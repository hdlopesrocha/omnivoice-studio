from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

from .audio import MIME_TYPES
from .runtime import (
    AppRuntime,
    JobCancelled,
    JobUnavailableError,
    JobValidationError,
)
from .schemas import TTSRequest
from .storage import utc_now

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
STATUS_PRIORITY = {
    "running": 0,
    "cancelling": 1,
    "queued": 2,
    "completed": 3,
    "failed": 4,
    "cancelled": 5,
}


class QueueFullError(RuntimeError):
    """Raised when the job queue has reached its configured limit."""


class Job:
    def __init__(
        self,
        job_id: str,
        job_type: str,
        summary: dict[str, Any],
        runner: Callable[["Job"], dict[str, Any]],
        cleanup_paths: list[Path] | None = None,
    ) -> None:
        self.id = job_id
        self.type = job_type
        self.summary = summary
        self._runner = runner
        self.cleanup_paths = list(cleanup_paths or [])

        self.status = "queued"
        self.progress = 0.0
        self.message = "Queued"
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.error_kind: str | None = None

        self.created_at = utc_now()
        self.created_ts = time.time()
        self.started_at: str | None = None
        self.started_ts: float | None = None
        self.finished_at: str | None = None
        self.finished_ts: float | None = None

        self.cancel_event = threading.Event()
        self.done_event = threading.Event()
        self._lock = threading.Lock()

    def run(self) -> dict[str, Any]:
        return self._runner(self)

    def mark_running(self) -> bool:
        with self._lock:
            if self.cancel_event.is_set():
                return False
            self.status = "running"
            self.started_at = utc_now()
            self.started_ts = time.time()
            self.message = "Starting…"
            return True

    def set_cancelling(self) -> None:
        with self._lock:
            if self.status in {"queued", "running"}:
                self.cancel_event.set()
                self.status = "cancelling"
                self.message = "Stopping after the current step…"

    def update_progress(self, progress: float, message: str) -> None:
        with self._lock:
            if self.status not in {"running", "cancelling"}:
                return
            if self.cancel_event.is_set() and self.status == "running":
                self.status = "cancelling"
                self.message = "Stopping after the current step…"
            if self.status == "running":
                self.progress = max(
                    self.progress, min(1.0, max(0.0, float(progress)))
                )
                if message:
                    self.message = message

    def finish(
        self,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        error_kind: str | None = None,
    ) -> None:
        with self._lock:
            if self.status in TERMINAL_STATUSES:
                return
            self.status = status
            if status == "completed":
                self.progress = 1.0
                self.message = "Completed"
            elif status == "cancelled":
                self.message = "Cancelled"
            else:
                self.message = "Failed"
            self.result = result
            self.error = error
            self.error_kind = error_kind
            self.finished_at = utc_now()
            self.finished_ts = time.time()
        self.done_event.set()

    def elapsed_seconds(self) -> float:
        if self.started_ts is None:
            return 0.0
        end = self.finished_ts or time.time()
        return round(max(0.0, end - self.started_ts), 1)

    def to_dict(self, queue_position: int | None = None) -> dict[str, Any]:
        with self._lock:
            status = self.status
            return {
                "id": self.id,
                "type": self.type,
                "status": status,
                "progress": round(self.progress, 3),
                "message": self.message,
                "queue_position": queue_position,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed_seconds": self.elapsed_seconds(),
                "summary": dict(self.summary),
                "result": dict(self.result) if self.result else None,
                "error": self.error,
                "error_kind": self.error_kind,
                "can_cancel": status in {"queued", "running"},
                "has_audio": (
                    status == "completed"
                    and self.type in {"tts", "voice_preview"}
                ),
            }


class JobManager:
    """A single-worker FIFO queue for model-bound work."""

    def __init__(
        self,
        runtime: AppRuntime,
        *,
        max_queue_size: int = 50,
        max_history: int = 200,
    ) -> None:
        self.runtime = runtime
        self.max_queue_size = max(1, max_queue_size)
        self.max_history = max(10, max_history)

        self._jobs: dict[str, Job] = {}
        self._queue: deque[Job] = deque()
        self._condition = threading.Condition()
        self._worker: threading.Thread | None = None
        self._stopping = False

    def start(self) -> None:
        with self._condition:
            self._stopping = False
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._loop,
                name="omnivoice-jobs",
                daemon=True,
            )
            self._worker.start()

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            queued = list(self._queue)
            self._queue.clear()
            for job in queued:
                job.cancel_event.set()
                job.finish(
                    "cancelled",
                    error="Engine is shutting down",
                    error_kind="cancelled",
                )
                self._cleanup(job)
            for job in self._jobs.values():
                if job.status in {"queued", "running"}:
                    job.cancel_event.set()
            self._condition.notify_all()
        if self._worker is not None:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                job = self._queue.popleft()

            if not job.mark_running():
                job.finish(
                    "cancelled",
                    error="Cancelled before starting",
                    error_kind="cancelled",
                )
                self._cleanup(job)
                self._prune()
                continue

            try:
                result = job.run()
                if job.cancel_event.is_set():
                    job.finish(
                        "cancelled",
                        error="Cancelled",
                        error_kind="cancelled",
                    )
                else:
                    job.finish("completed", result=result)
            except JobCancelled as exc:
                job.finish(
                    "cancelled",
                    error=str(exc) or "Cancelled",
                    error_kind="cancelled",
                )
            except JobValidationError as exc:
                job.finish(
                    "failed",
                    error=str(exc),
                    error_kind="validation",
                )
            except JobUnavailableError as exc:
                job.finish(
                    "failed",
                    error=str(exc),
                    error_kind="unavailable",
                )
            except Exception as exc:
                logger.exception("Job %s failed", job.id)
                job.finish(
                    "failed",
                    error=str(exc),
                    error_kind="internal",
                )
            finally:
                self._cleanup(job)
                self._prune()

    def _submit(
        self,
        job_type: str,
        summary: dict[str, Any],
        runner: Callable[[Job], dict[str, Any]],
        cleanup_paths: list[Path] | None = None,
    ) -> Job:
        with self._condition:
            if self._stopping:
                raise RuntimeError("The job worker is shutting down")
            if len(self._queue) >= self.max_queue_size:
                raise QueueFullError(
                    f"The queue is full ({self.max_queue_size} jobs). "
                    "Wait for a job to finish or cancel a queued job."
                )
            job = Job(
                uuid.uuid4().hex[:12],
                job_type,
                summary,
                runner,
                cleanup_paths,
            )
            self._jobs[job.id] = job
            self._queue.append(job)
            self._condition.notify()
            return job

    def submit_tts(
        self,
        req: TTSRequest,
        summary: dict[str, Any],
    ) -> Job:
        def runner(job: Job) -> dict[str, Any]:
            return self.runtime.run_tts(
                req,
                job.cancel_event,
                job.update_progress,
            )

        return self._submit("tts", summary, runner)

    def submit_voice(
        self,
        *,
        name: str,
        language: str | None,
        transcript: str | None,
        transcript_provided: bool,
        audio_path: Path,
        summary: dict[str, Any],
    ) -> Job:
        def runner(job: Job) -> dict[str, Any]:
            return self.runtime.train_voice(
                name=name,
                language=language,
                transcript=transcript,
                transcript_provided=transcript_provided,
                audio_path=audio_path,
                voice_id=None,
                cancel_event=job.cancel_event,
                progress=job.update_progress,
            )

        return self._submit(
            "voice_train",
            summary,
            runner,
            cleanup_paths=[audio_path],
        )

    def submit_retrain(
        self,
        *,
        voice_id: str,
        name: str | None,
        language: str | None,
        transcript: str | None,
        transcript_provided: bool,
        audio_path: Path | None,
        summary: dict[str, Any],
    ) -> Job:
        def runner(job: Job) -> dict[str, Any]:
            return self.runtime.train_voice(
                name=name or "",
                language=language,
                transcript=transcript,
                transcript_provided=transcript_provided,
                audio_path=audio_path,
                voice_id=voice_id,
                cancel_event=job.cancel_event,
                progress=job.update_progress,
            )

        return self._submit(
            "voice_retrain",
            summary,
            runner,
            cleanup_paths=[audio_path] if audio_path else None,
        )

    def submit_preview(
        self,
        *,
        voice_id: str,
        text: str | None,
        summary: dict[str, Any],
    ) -> Job:
        def runner(job: Job) -> dict[str, Any]:
            return self.runtime.generate_preview(
                voice_id=voice_id,
                text=text,
                cancel_event=job.cancel_event,
                progress=job.update_progress,
            )

        return self._submit("voice_preview", summary, runner)

    def _queued_ids(self) -> list[str]:
        return [job.id for job in self._queue if job.status == "queued"]

    def public(
        self,
        job: Job,
        queued_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if queued_ids is None:
            with self._condition:
                queued_ids = self._queued_ids()
        position = None
        if job.status == "queued" and job.id in queued_ids:
            position = queued_ids.index(job.id) + 1
        return job.to_dict(position)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._condition:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError("Job not found")
        return self.public(job)

    def list_jobs(self, limit: int = 100) -> dict[str, Any]:
        with self._condition:
            queued_ids = self._queued_ids()
            jobs = list(self._jobs.values())
            counts = {"queued": 0, "running": 0, "cancelling": 0}
            for job in jobs:
                if job.status in counts:
                    counts[job.status] += 1
        jobs.sort(
            key=lambda job: (
                STATUS_PRIORITY.get(job.status, 9),
                -job.created_ts,
            )
        )
        return {
            "jobs": [
                self.public(job, queued_ids) for job in jobs[: max(0, limit)]
            ],
            "counts": counts,
            "active": counts["queued"] + counts["running"] + counts["cancelling"],
        }

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError("Job not found")
            if job.status in TERMINAL_STATUSES:
                return self.public(job)

            job.cancel_event.set()
            if job.status == "queued":
                try:
                    self._queue.remove(job)
                except ValueError:
                    pass
                job.finish(
                    "cancelled",
                    error="Cancelled before starting",
                    error_kind="cancelled",
                )
                self._cleanup(job)
                self._prune()
            elif job.status == "running":
                job.set_cancelling()
        return self.public(job)

    def cancel_queued(self) -> int:
        with self._condition:
            queued = list(self._queue)
            self._queue.clear()
            for job in queued:
                job.cancel_event.set()
                job.finish(
                    "cancelled",
                    error="Cancelled before starting",
                    error_kind="cancelled",
                )
                self._cleanup(job)
        if queued:
            self._prune()
        return len(queued)

    def delete(self, job_id: str) -> None:
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError("Job not found")
            if job.status not in TERMINAL_STATUSES:
                raise ValueError("Cannot delete a queued or running job")
            del self._jobs[job_id]

    def audio_path(self, job_id: str) -> tuple[Path, str]:
        with self._condition:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError("Job not found")
        if job.status != "completed":
            raise ValueError("Job audio is not available")
        result = job.result or {}

        if job.type == "tts":
            output_id = result.get("output_id") or result.get("id")
            if not output_id:
                raise KeyError("Job has no output")
            meta = self.runtime.outputs.get_meta(output_id)
            path = self.runtime.outputs.audio_path(meta)
            fmt = str(meta.get("format") or "wav")
            return path, MIME_TYPES.get(fmt, "application/octet-stream")

        if job.type == "voice_preview":
            voice_id = result.get("voice_id")
            if not voice_id:
                raise KeyError("Job has no preview")
            path = self.runtime.voices.preview_path(voice_id)
            if not path.is_file():
                raise KeyError("Preview has been removed")
            return path, "audio/wav"

        raise KeyError("Job has no audio")

    def _cleanup(self, job: Job) -> None:
        for path in job.cleanup_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Could not remove temporary file %s", path)
        job.cleanup_paths.clear()

    def _prune(self) -> None:
        with self._condition:
            terminal = [
                job
                for job in self._jobs.values()
                if job.status in TERMINAL_STATUSES
            ]
            if len(terminal) <= self.max_history:
                return
            terminal.sort(key=lambda job: job.finished_ts or job.created_ts)
            for job in terminal[: len(terminal) - self.max_history]:
                self._jobs.pop(job.id, None)

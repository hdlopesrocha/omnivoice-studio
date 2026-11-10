from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import shutil
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.routing import APIRouter

from .audio import MIME_TYPES, probe_duration
from .config import Settings
from .jobs import Job, JobManager, QueueFullError
from .languages import LANGUAGE_PAYLOAD
from .model_manager import ModelManager
from .runtime import AppRuntime, PORTUGUESE_VARIANTS
from .schemas import (
    BatchTTSRequest,
    OpenAISpeechRequest,
    TTSRequest,
    VoiceRename,
)
from .storage import OutputStore, VoiceStore, utc_now

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("omnivoice.studio")

settings = Settings.from_env()
voices = VoiceStore(settings.voices_dir)
outputs = OutputStore(settings.outputs_dir)
manager = ModelManager(settings)
runtime = AppRuntime(settings, voices, outputs, manager)
jobs = JobManager(
    runtime,
    max_queue_size=settings.max_queue_size,
    max_history=settings.max_job_history,
)

OPENAI_VOICE_ALIASES = {
    "auto",
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    voices.ensure()
    outputs.ensure()
    try:
        settings.tmp_dir.mkdir(parents=True, exist_ok=True)
        for stale in settings.tmp_dir.iterdir():
            if stale.is_file():
                stale.unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "Could not clean the temporary upload directory %s",
            settings.tmp_dir,
            exc_info=True,
        )
    manager.start_loading()
    jobs.start()
    try:
        yield
    finally:
        jobs.stop()


app = FastAPI(
    title="OmniVoice Studio API",
    description=(
        "Local, Dockerized OmniVoice engine with reusable voice profiles, "
        "voice design, a cancellable job queue, and generation history."
    ),
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Output-Id",
        "X-Audio-Duration",
        "X-Generation-Seconds",
        "X-RTF",
        "Content-Disposition",
    ],
)

router = APIRouter(prefix="/api")


def _public_voice(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta.get("id"),
        "name": meta.get("name"),
        "language": meta.get("language"),
        "transcript": meta.get("transcript"),
        "duration_seconds": meta.get("duration_seconds", 0),
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "has_preview": bool(meta.get("has_preview")),
        "preview_updated_at": meta.get("preview_updated_at"),
    }


def _public_output(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta.get("id"),
        "text": meta.get("text"),
        "text_preview": meta.get("text_preview"),
        "mode": meta.get("mode"),
        "voice_id": meta.get("voice_id"),
        "voice_name": meta.get("voice_name"),
        "instruct": meta.get("instruct"),
        "language": meta.get("language"),
        "language_variant": meta.get("language_variant"),
        "format": meta.get("format"),
        "duration_seconds": meta.get("duration_seconds", 0),
        "generation_seconds": meta.get("generation_seconds", 0),
        "rtf": meta.get("rtf"),
        "seed": meta.get("seed"),
        "created_at": meta.get("created_at"),
        "size_bytes": meta.get("size_bytes", 0),
    }


def _audio_headers(meta: dict[str, Any]) -> dict[str, str]:
    rtf = meta.get("rtf")
    return {
        "X-Output-Id": str(meta["id"]),
        "X-Audio-Duration": f"{float(meta.get('duration_seconds') or 0):.3f}",
        "X-Generation-Seconds": f"{float(meta.get('generation_seconds') or 0):.3f}",
        "X-RTF": f"{float(rtf):.4f}" if rtf is not None else "",
        "Content-Disposition": (
            f'inline; filename="omnivoice-{meta["id"]}.{meta["format"]}"'
        ),
    }


async def _read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Audio upload is larger than "
                    f"{max_bytes // (1024 * 1024)} MB"
                ),
            )
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="Audio upload is empty")
    return b"".join(chunks)


def _safe_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if 1 < len(suffix) <= 9 and suffix[1:].isalnum():
        return suffix
    return ".bin"


async def _save_upload_temp(audio: UploadFile) -> Path:
    data = await _read_upload(audio, settings.max_upload_mb * 1024 * 1024)
    path = settings.tmp_dir / f"{uuid.uuid4().hex}{_safe_suffix(audio.filename)}"
    try:
        settings.tmp_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:
        logger.exception("Could not store uploaded audio in %s", settings.tmp_dir)
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not store the uploaded audio. Check that the data "
                f"volume is writable: {exc}"
            ),
        ) from exc
    return path


def _cleanup_paths(paths: list[Path | None]) -> None:
    for path in paths:
        if path is not None:
            path.unlink(missing_ok=True)


def _find_voice(value: str) -> dict[str, Any] | None:
    needle = value.strip().lower()
    if not needle:
        return None
    for meta in voices.list_meta():
        if str(meta.get("id", "")).lower() == needle:
            return meta
        if str(meta.get("name", "")).strip().lower() == needle:
            return meta
    return None


def _validate_tts(req: TTSRequest) -> dict[str, Any] | None:
    voice_meta: dict[str, Any] | None = None
    if req.mode == "voice":
        if not req.voice_id:
            raise HTTPException(
                status_code=400,
                detail="voice_id is required when mode is 'voice'",
            )
        try:
            voice_meta = voices.get_meta(req.voice_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Voice not found") from exc
        if not voices.prompt_path(req.voice_id).is_file():
            raise HTTPException(
                status_code=409,
                detail="This voice has no trained prompt. Retrain it first.",
            )
    elif req.mode == "design" and not req.instruct:
        raise HTTPException(
            status_code=400,
            detail="instruct is required when mode is 'design'",
        )

    variant = req.language_variant or (
        req.language if req.language in PORTUGUESE_VARIANTS else None
    )
    if variant in PORTUGUESE_VARIANTS:
        if req.mode != "voice":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{variant} requires a trained voice profile recorded "
                    "with a matching reference clip. Auto voice and voice "
                    "design cannot guarantee the accent."
                ),
            )
        if voice_meta is None or voice_meta.get("language") != variant:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This voice is tagged "
                    f"{voice_meta.get('language') if voice_meta else 'unknown'}"
                    f", not {variant}. Retrain or tag the voice with a "
                    "matching reference clip first."
                ),
            )
    return voice_meta


def _tts_summary(
    req: TTSRequest,
    voice_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "kind": "tts",
        "text_preview": req.text[:140],
        "mode": req.mode,
        "voice_id": req.voice_id if req.mode == "voice" else None,
        "voice_name": voice_meta.get("name") if voice_meta else None,
        "language": req.language
        or (voice_meta.get("language") if voice_meta else None),
        "language_variant": req.language_variant
        or (
            req.language
            if req.language in PORTUGUESE_VARIANTS
            else (
                voice_meta.get("language")
                if voice_meta
                and voice_meta.get("language") in PORTUGUESE_VARIANTS
                else None
            )
        ),
        "style_instruct": (
            req.style_instruct if req.mode == "voice" else None
        ),
        "seed": req.seed,
        "format": req.response_format,
    }


def _submit_tts(
    req: TTSRequest,
    voice_meta: dict[str, Any] | None,
) -> Job:
    try:
        return jobs.submit_tts(req, _tts_summary(req, voice_meta))
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _wait_job(job: Job) -> dict[str, Any]:
    await asyncio.to_thread(job.done_event.wait)
    if job.status == "cancelled":
        raise HTTPException(
            status_code=409,
            detail=job.error or "The job was cancelled",
        )
    if job.status == "failed":
        if job.error_kind == "validation":
            status_code = 400
        elif job.error_kind == "unavailable":
            status_code = 503
        else:
            status_code = 500
        raise HTTPException(
            status_code=status_code,
            detail=job.error or "The job failed",
        )
    if job.result is None:
        raise HTTPException(
            status_code=500,
            detail="The job completed without a result",
        )
    return job.result


@router.get("/health", tags=["System"])
async def health() -> dict[str, Any]:
    job_state = jobs.list_jobs(limit=1)
    return {
        "status": manager.status,
        "model_loaded": manager.model_loaded,
        "device": manager.device,
        "model_id": settings.model_id,
        "asr_model": settings.asr_model,
        "asr_loaded": manager.asr_loaded,
        "message": manager.status_message,
        "error": manager.error,
        "uptime_seconds": manager.uptime_seconds,
        "load_seconds": manager.load_seconds,
        "sample_rate": manager.sample_rate,
        "voices": len(voices.list_meta()),
        "outputs": outputs.count(),
        "jobs": job_state["active"],
        "lora_adapter": manager.lora_adapter,
        "flashinfer": manager.flashinfer_enabled,
        "version": settings.app_version,
    }


@router.get("/info", tags=["System"])
async def info() -> dict[str, Any]:
    return {
        "name": "OmniVoice Studio",
        "version": settings.app_version,
        "model_id": settings.model_id,
        "device": manager.device,
        "sample_rate": manager.sample_rate,
        "max_input_chars": settings.max_input_chars,
        "max_upload_mb": settings.max_upload_mb,
        "min_voice_seconds": settings.min_voice_seconds,
        "max_voice_seconds": settings.max_voice_seconds,
        "max_queue_size": settings.max_queue_size,
        "max_job_history": settings.max_job_history,
        "max_import_mb": settings.max_import_mb,
        "lora_adapter": manager.lora_adapter,
        "flashinfer": manager.flashinfer_enabled,
        "normalize_text": True,
        "formats": list(MIME_TYPES),
        "modes": ["voice", "design", "auto"],
        "preview_text": settings.preview_text,
        "languages": len(LANGUAGE_PAYLOAD["languages"]),
    }


@router.get("/languages", tags=["System"])
async def languages() -> dict[str, Any]:
    return LANGUAGE_PAYLOAD


@router.post("/model/reload", tags=["System"])
async def reload_model() -> dict[str, str]:
    await asyncio.to_thread(manager.reload)
    return {"status": "loading"}


# ── Job queue ──────────────────────────────────────────────────────────────


@router.get("/jobs", tags=["Jobs"])
async def list_jobs(
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    return jobs.list_jobs(limit)


@router.post("/jobs/cancel-queued", tags=["Jobs"])
async def cancel_queued_jobs() -> dict[str, int]:
    return {"cancelled": jobs.cancel_queued()}


@router.post("/jobs/tts", status_code=202, tags=["Jobs"])
async def submit_tts_job(req: TTSRequest) -> dict[str, Any]:
    voice_meta = _validate_tts(req)
    job = _submit_tts(req, voice_meta)
    return jobs.public(job)


@router.post("/jobs/batch", status_code=202, tags=["Jobs"])
async def submit_batch_job(req: BatchTTSRequest) -> dict[str, Any]:
    probe = req.to_tts_request(req.texts[0])
    voice_meta = _validate_tts(probe)
    summary = _tts_summary(probe, voice_meta)
    summary["kind"] = "tts_batch"
    summary["count"] = len(req.texts)
    summary["text_preview"] = req.texts[0][:140]
    try:
        job = jobs.submit_batch(req, summary)
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return jobs.public(job)


@router.post("/jobs/transcribe", status_code=202, tags=["Jobs"])
async def submit_transcribe_job(
    audio: UploadFile = File(...),
) -> dict[str, Any]:
    audio_path = await _save_upload_temp(audio)
    summary = {
        "kind": "transcribe",
        "filename": audio.filename or audio_path.name,
    }
    try:
        job = jobs.submit_transcribe(
            audio_path=audio_path,
            summary=summary,
        )
    except QueueFullError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return jobs.public(job)


@router.post("/jobs/voices", status_code=202, tags=["Jobs"])
async def submit_voice_job(
    name: str = Form(..., max_length=60),
    audio: UploadFile = File(...),
    transcript: str | None = Form(None),
    language: str | None = Form(None),
    consent: bool = Form(False),
    preprocess_prompt: bool = Form(True),
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Voice name is required")
    if not consent:
        raise HTTPException(
            status_code=400,
            detail=(
                "Consent confirmation is required. Only clone voices you own "
                "or have explicit permission to use."
            ),
        )

    transcript_clean = (transcript or "").strip() or None
    language_clean = (language or "").strip() or None
    audio_path = await _save_upload_temp(audio)

    summary = {
        "kind": "voice_train",
        "name": name,
        "language": language_clean,
        "transcript_provided": transcript is not None,
    }
    try:
        job = jobs.submit_voice(
            name=name,
            language=language_clean,
            transcript=transcript_clean,
            transcript_provided=transcript is not None,
            audio_path=audio_path,
            preprocess_prompt=preprocess_prompt,
            summary=summary,
        )
    except QueueFullError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return jobs.public(job)


@router.post(
    "/jobs/voices/{voice_id}/retrain",
    status_code=202,
    tags=["Jobs"],
)
async def submit_retrain_job(
    voice_id: str,
    audio: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    language: str | None = Form(None),
    name: str | None = Form(None, max_length=60),
    consent: bool = Form(False),
    preprocess_prompt: bool = Form(True),
) -> dict[str, Any]:
    try:
        meta = voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    if not consent:
        raise HTTPException(
            status_code=400,
            detail=(
                "Consent confirmation is required. Only clone voices you own "
                "or have explicit permission to use."
            ),
        )
    if audio is None and transcript is None and language is None and name is None:
        raise HTTPException(
            status_code=400,
            detail="Provide new audio, a transcript, a language, or a name",
        )

    new_name = (name or "").strip() if name is not None else None
    if name is not None and not new_name:
        raise HTTPException(status_code=400, detail="Voice name cannot be empty")

    audio_path = await _save_upload_temp(audio) if audio is not None else None
    summary = {
        "kind": "voice_retrain",
        "voice_id": voice_id,
        "name": new_name or meta.get("name"),
        "language": (
            (language or "").strip() or None
            if language is not None
            else meta.get("language")
        ),
        "transcript_provided": transcript is not None,
    }
    try:
        job = jobs.submit_retrain(
            voice_id=voice_id,
            name=new_name,
            language=language,
            transcript=transcript,
            transcript_provided=transcript is not None,
            audio_path=audio_path,
            preprocess_prompt=preprocess_prompt,
            summary=summary,
        )
    except QueueFullError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return jobs.public(job)


@router.post(
    "/jobs/voices/{voice_id}/preview",
    status_code=202,
    tags=["Jobs"],
)
async def submit_preview_job(
    voice_id: str,
    text: str | None = Query(None, max_length=300),
) -> dict[str, Any]:
    try:
        meta = voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    if not voices.prompt_path(voice_id).is_file():
        raise HTTPException(
            status_code=409,
            detail="This voice has no trained prompt. Retrain it first.",
        )
    summary = {
        "kind": "voice_preview",
        "voice_id": voice_id,
        "voice_name": meta.get("name"),
        "text": (text or settings.preview_text)[:140],
    }
    try:
        job = jobs.submit_preview(
            voice_id=voice_id,
            text=text,
            summary=summary,
        )
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return jobs.public(job)


@router.get("/jobs/{job_id}", tags=["Jobs"])
async def get_job(job_id: str) -> dict[str, Any]:
    try:
        return jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.post("/jobs/{job_id}/cancel", tags=["Jobs"])
async def cancel_job(job_id: str) -> dict[str, Any]:
    try:
        return jobs.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.delete("/jobs/{job_id}", tags=["Jobs"])
async def delete_job(job_id: str) -> dict[str, bool]:
    try:
        jobs.delete(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/jobs/{job_id}/audio", tags=["Jobs"])
async def get_job_audio(
    job_id: str,
    download: bool = Query(False),
) -> FileResponse:
    try:
        path, media_type = jobs.audio_path(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    filename = f"omnivoice-{job_id}{path.suffix}" if download else None
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/jobs/{job_id}/zip", tags=["Jobs"])
async def get_batch_zip(job_id: str) -> Response:
    try:
        items = jobs.batch_items(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    buffer = io.BytesIO()
    manifest: list[dict[str, Any]] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, meta in enumerate(items, start=1):
            try:
                path = outputs.audio_path(meta)
            except KeyError:
                continue
            archive.write(
                path,
                arcname=f"{index:02d}-{meta['id']}.{meta['format']}",
            )
            manifest.append(
                {
                    "index": index,
                    "output_id": meta.get("id"),
                    "text": meta.get("text"),
                    "voice_name": meta.get("voice_name"),
                    "language": meta.get("language"),
                    "language_variant": meta.get("language_variant"),
                    "duration_seconds": meta.get("duration_seconds"),
                    "format": meta.get("format"),
                }
            )
        archive.writestr(
            "metadata.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="omnivoice-batch-{job_id}.zip"'
            )
        },
    )


# ── Voices ─────────────────────────────────────────────────────────────────


@router.get("/voices", tags=["Voices"])
async def list_voices() -> dict[str, Any]:
    return {"voices": [_public_voice(meta) for meta in voices.list_meta()]}


@router.get("/voices/{voice_id}", tags=["Voices"])
async def get_voice(voice_id: str) -> dict[str, Any]:
    try:
        return _public_voice(voices.get_meta(voice_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc


@router.post("/voices", status_code=201, tags=["Voices"])
async def create_voice(
    name: str = Form(..., max_length=60),
    audio: UploadFile = File(...),
    transcript: str | None = Form(None),
    language: str | None = Form(None),
    consent: bool = Form(False),
    preprocess_prompt: bool = Form(True),
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Voice name is required")
    if not consent:
        raise HTTPException(
            status_code=400,
            detail=(
                "Consent confirmation is required. Only clone voices you own "
                "or have explicit permission to use."
            ),
        )

    transcript_clean = (transcript or "").strip() or None
    language_clean = (language or "").strip() or None
    audio_path = await _save_upload_temp(audio)
    summary = {
        "kind": "voice_train",
        "name": name,
        "language": language_clean,
        "transcript_provided": transcript is not None,
    }
    try:
        job = jobs.submit_voice(
            name=name,
            language=language_clean,
            transcript=transcript_clean,
            transcript_provided=transcript is not None,
            audio_path=audio_path,
            preprocess_prompt=preprocess_prompt,
            summary=summary,
        )
    except QueueFullError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = await _wait_job(job)
    return _public_voice(result)


@router.post("/voices/{voice_id}/retrain", tags=["Voices"])
async def retrain_voice(
    voice_id: str,
    audio: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    language: str | None = Form(None),
    name: str | None = Form(None, max_length=60),
    consent: bool = Form(False),
    preprocess_prompt: bool = Form(True),
) -> dict[str, Any]:
    try:
        meta = voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    if not consent:
        raise HTTPException(
            status_code=400,
            detail=(
                "Consent confirmation is required. Only clone voices you own "
                "or have explicit permission to use."
            ),
        )
    if audio is None and transcript is None and language is None and name is None:
        raise HTTPException(
            status_code=400,
            detail="Provide new audio, a transcript, a language, or a name",
        )

    new_name = (name or "").strip() if name is not None else None
    if name is not None and not new_name:
        raise HTTPException(status_code=400, detail="Voice name cannot be empty")

    audio_path = await _save_upload_temp(audio) if audio is not None else None
    summary = {
        "kind": "voice_retrain",
        "voice_id": voice_id,
        "name": new_name or meta.get("name"),
        "language": (
            (language or "").strip() or None
            if language is not None
            else meta.get("language")
        ),
        "transcript_provided": transcript is not None,
    }
    try:
        job = jobs.submit_retrain(
            voice_id=voice_id,
            name=new_name,
            language=language,
            transcript=transcript,
            transcript_provided=transcript is not None,
            audio_path=audio_path,
            preprocess_prompt=preprocess_prompt,
            summary=summary,
        )
    except QueueFullError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = await _wait_job(job)
    return _public_voice(result)


@router.patch("/voices/{voice_id}", tags=["Voices"])
async def rename_voice(voice_id: str, payload: VoiceRename) -> dict[str, Any]:
    try:
        meta = voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    meta["name"] = payload.name
    meta["updated_at"] = utc_now()
    voices.save_meta(voice_id, meta)
    return _public_voice(meta)


@router.delete("/voices/{voice_id}", tags=["Voices"])
async def delete_voice(voice_id: str) -> dict[str, bool]:
    try:
        voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    manager.invalidate_voice(voice_id)
    voices.delete(voice_id)
    return {"ok": True}


@router.get("/voices/{voice_id}/reference", tags=["Voices"])
async def get_reference(voice_id: str) -> FileResponse:
    try:
        voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    path = voices.reference_path(voice_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Reference audio not found")
    return FileResponse(path, media_type="audio/wav")


@router.get("/voices/{voice_id}/preview", tags=["Voices"])
async def get_preview(voice_id: str) -> FileResponse:
    try:
        voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    path = voices.preview_path(voice_id)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Preview has not been generated",
        )
    return FileResponse(path, media_type="audio/wav")


@router.get("/voices/{voice_id}/export", tags=["Voices"])
async def export_voice(voice_id: str) -> Response:
    try:
        meta = voices.get_meta(voice_id)
        reference = voices.reference_path(voice_id)
        prompt = voices.prompt_path(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    if not reference.is_file() or not prompt.is_file():
        raise HTTPException(
            status_code=409,
            detail="Voice profile is incomplete and cannot be exported",
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "meta.json",
            json.dumps(meta, ensure_ascii=False, indent=2),
        )
        archive.write(reference, arcname="reference.wav")
        archive.write(prompt, arcname="prompt.pt")
        preview = voices.preview_path(voice_id)
        if preview.is_file():
            archive.write(preview, arcname="preview.wav")
    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="omnivoice-voice-{voice_id}.zip"'
            )
        },
    )


@router.post("/voices/import", status_code=201, tags=["Voices"])
async def import_voice(archive: UploadFile = File(...)) -> dict[str, Any]:
    data = await _read_upload(
        archive,
        settings.max_import_mb * 1024 * 1024,
    )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            names = set(bundle.namelist())
            required = {"meta.json", "reference.wav", "prompt.pt"}
            if not required.issubset(names):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Voice archive must contain meta.json, "
                        "reference.wav, and prompt.pt"
                    ),
                )
            meta = json.loads(bundle.read("meta.json"))
            if not isinstance(meta, dict):
                raise HTTPException(
                    status_code=400,
                    detail="meta.json must contain a JSON object",
                )
            reference_bytes = bundle.read("reference.wav")
            prompt_bytes = bundle.read("prompt.pt")
            preview_bytes = (
                bundle.read("preview.wav")
                if "preview.wav" in names
                else None
            )
    except HTTPException:
        raise
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice archive: {exc}",
        ) from exc

    voice_id, _ = voices.create()
    try:
        reference_path = voices.reference_path(voice_id)
        reference_path.write_bytes(reference_bytes)
        duration = probe_duration(reference_path)
        if duration < settings.min_voice_seconds:
            raise HTTPException(
                status_code=400,
                detail="Imported reference audio is too short",
            )
        if duration > settings.max_voice_seconds:
            raise HTTPException(
                status_code=400,
                detail="Imported reference audio is too long",
            )

        prompt_path = voices.prompt_path(voice_id)
        prompt_path.write_bytes(prompt_bytes)
        manager.load_prompt(voice_id, prompt_path)

        preview_path = voices.preview_path(voice_id)
        if preview_bytes:
            preview_path.write_bytes(preview_bytes)

        now = utc_now()
        name = str(meta.get("name") or "Imported voice").strip()
        meta = {
            **meta,
            "id": voice_id,
            "name": name or "Imported voice",
            "duration_seconds": round(duration, 3),
            "sample_rate": 24_000,
            "created_at": now,
            "updated_at": now,
            "has_preview": bool(preview_bytes),
            "preview_updated_at": now if preview_bytes else None,
            "reference_filename": "reference.wav",
            "prompt_filename": "prompt.pt",
        }
        voices.save_meta(voice_id, meta)
        return _public_voice(meta)
    except HTTPException:
        voices.delete(voice_id)
        raise
    except Exception as exc:
        voices.delete(voice_id)
        logger.exception("Voice import failed")
        raise HTTPException(
            status_code=400,
            detail=f"Could not import voice profile: {exc}",
        ) from exc


@router.post("/voices/{voice_id}/preview", tags=["Voices"])
async def create_preview(
    voice_id: str,
    text: str | None = Query(None, max_length=300),
) -> Response:
    try:
        meta = voices.get_meta(voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    if not voices.prompt_path(voice_id).is_file():
        raise HTTPException(
            status_code=409,
            detail="This voice has no trained prompt. Retrain it first.",
        )
    summary = {
        "kind": "voice_preview",
        "voice_id": voice_id,
        "voice_name": meta.get("name"),
        "text": (text or settings.preview_text)[:140],
    }
    try:
        job = jobs.submit_preview(
            voice_id=voice_id,
            text=text,
            summary=summary,
        )
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = await _wait_job(job)
    path = voices.preview_path(voice_id)
    if not path.is_file():
        raise HTTPException(status_code=500, detail="Preview file is missing")
    return Response(
        content=path.read_bytes(),
        media_type="audio/wav",
        headers={
            "X-Audio-Duration": f"{float(result.get('duration_seconds') or 0):.3f}",
            "X-Generation-Seconds": (
                f"{float(result.get('generation_seconds') or 0):.3f}"
            ),
            "Content-Disposition": (
                f'inline; filename="preview-{voice_id}.wav"'
            ),
        },
    )


@router.post("/batch", tags=["Speech"])
async def batch_tts(req: BatchTTSRequest) -> dict[str, Any]:
    probe = req.to_tts_request(req.texts[0])
    voice_meta = _validate_tts(probe)
    summary = _tts_summary(probe, voice_meta)
    summary["kind"] = "tts_batch"
    summary["count"] = len(req.texts)
    summary["text_preview"] = req.texts[0][:140]
    try:
        job = jobs.submit_batch(req, summary)
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await _wait_job(job)


@router.post("/transcribe", tags=["Speech"])
async def transcribe(audio: UploadFile = File(...)) -> dict[str, Any]:
    audio_path = await _save_upload_temp(audio)
    summary = {
        "kind": "transcribe",
        "filename": audio.filename or audio_path.name,
    }
    try:
        job = jobs.submit_transcribe(
            audio_path=audio_path,
            summary=summary,
        )
    except QueueFullError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        _cleanup_paths([audio_path])
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await _wait_job(job)


# ── Speech ─────────────────────────────────────────────────────────────────


@router.post("/tts", tags=["Speech"])
async def tts(req: TTSRequest) -> Response:
    voice_meta = _validate_tts(req)
    job = _submit_tts(req, voice_meta)
    result = await _wait_job(job)
    try:
        path = outputs.audio_path(result)
    except KeyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated audio file is missing",
        ) from exc
    return Response(
        content=path.read_bytes(),
        media_type=MIME_TYPES[result["format"]],
        headers=_audio_headers(result),
    )


@router.get("/outputs", tags=["History"])
async def list_outputs(
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    return {
        "outputs": [
            _public_output(meta) for meta in outputs.list_meta(limit)
        ]
    }


@router.get("/outputs/{output_id}", tags=["History"])
async def get_output(
    output_id: str,
    download: bool = Query(False),
) -> FileResponse:
    try:
        meta = outputs.get_meta(output_id)
        path = outputs.audio_path(meta)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Output not found") from exc

    fmt = str(meta.get("format") or path.suffix.lstrip("."))
    filename = f"omnivoice-{output_id}.{fmt}" if download else None
    return FileResponse(
        path,
        media_type=MIME_TYPES.get(fmt, "application/octet-stream"),
        filename=filename,
    )


@router.delete("/outputs/{output_id}", tags=["History"])
async def delete_output(output_id: str) -> dict[str, bool]:
    try:
        outputs.delete(output_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Output not found") from exc
    return {"ok": True}


@router.post("/v1/audio/speech", tags=["OpenAI compatible"])
async def openai_speech(req: OpenAISpeechRequest) -> Response:
    """Small OpenAI-compatible shim for clients that expect /v1/audio/speech."""
    voice = (req.voice or "auto").strip()
    mode: str = "auto"
    voice_id: str | None = None
    instruct: str | None = req.instruct

    if voice.lower() not in OPENAI_VOICE_ALIASES:
        found = _find_voice(voice)
        if found is not None:
            mode = "voice"
            voice_id = str(found["id"])
        elif voice.lower().startswith("design:"):
            mode = "design"
            instruct = voice.split(":", 1)[1].strip() or instruct
        else:
            mode = "design"
            instruct = voice

    tts_req = TTSRequest(
        text=req.input,
        mode=mode,  # type: ignore[arg-type]
        voice_id=voice_id,
        instruct=instruct,
        style_instruct=req.style_instruct,
        language=req.language,
        language_variant=req.language_variant,
        speed=req.speed,
        normalize_text=req.normalize_text,
        seed=req.seed,
        response_format=req.response_format,
    )
    voice_meta = _validate_tts(tts_req)
    job = _submit_tts(tts_req, voice_meta)
    result = await _wait_job(job)
    try:
        path = outputs.audio_path(result)
    except KeyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated audio file is missing",
        ) from exc
    return Response(
        content=path.read_bytes(),
        media_type=MIME_TYPES[result["format"]],
        headers=_audio_headers(result),
    )


@router.get("/v1/models", tags=["OpenAI compatible"])
async def openai_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "omnivoice",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
            }
        ],
    }


@router.get("/v1/voices", tags=["OpenAI compatible"])
async def openai_voices() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": meta.get("id"),
                "name": meta.get("name"),
                "language": meta.get("language"),
                "duration_seconds": meta.get("duration_seconds"),
            }
            for meta in voices.list_meta()
        ],
    }


app.include_router(router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": "OmniVoice Studio API",
        "docs": "/api/docs",
        "health": "/api/health",
        "jobs": "/api/jobs",
    }

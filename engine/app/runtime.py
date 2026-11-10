from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .audio import (
    AudioConversionError,
    convert_to_wav,
    encode_audio,
    probe_duration,
    write_wav,
)
from .config import Settings
from .model_manager import ModelManager, ModelNotReadyError
from .schemas import BatchTTSRequest, TTSRequest
from .storage import OutputStore, VoiceStore, utc_now

ProgressFn = Callable[[float, str], None]
CancelEvent = threading.Event
PORTUGUESE_VARIANTS = {"pt-PT", "pt-BR"}


def normalize_model_language(language: str | None) -> str | None:
    """OmniVoice has one `pt` model language; variants are profile tags."""
    if language in PORTUGUESE_VARIANTS:
        return "pt"
    return language


def preview_text_for_language(
    language: str | None,
    default: str,
) -> str:
    if language == "pt-PT":
        return (
            "Olá! Esta é uma pré-visualização da minha voz em português "
            "de Portugal."
        )
    if language == "pt-BR":
        return (
            "Olá! Esta é uma prévia da minha voz em português do Brasil."
        )
    return default


class JobCancelled(RuntimeError):
    """Raised when a job notices its cancellation flag."""


class JobValidationError(RuntimeError):
    """A user-facing validation error (maps to HTTP 400)."""


class JobUnavailableError(RuntimeError):
    """The model is not ready (maps to HTTP 503)."""


def split_text_for_jobs(text: str, max_chars: int = 420) -> list[str]:
    """Split long text at sentence/paragraph boundaries.

    The split lets the worker check for cancellation between model calls.
    Short text remains a single call because OmniVoice generation itself is
    not preemptible.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    pieces = re.split(r"(?<=[.!?…。！？])\s+|\n+", text)
    chunks: list[str] = []
    current = ""

    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue

        if len(piece) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = piece.split()
            buffer = ""
            for word in words:
                if not buffer:
                    buffer = word
                elif len(buffer) + 1 + len(word) <= max_chars:
                    buffer = f"{buffer} {word}"
                else:
                    chunks.append(buffer)
                    buffer = word
            if buffer:
                chunks.append(buffer)
            continue

        if not current:
            current = piece
        elif len(current) + 1 + len(piece) <= max_chars:
            current = f"{current} {piece}"
        else:
            chunks.append(current)
            current = piece

    if current:
        chunks.append(current)
    return chunks or [text]


class AppRuntime:
    """Core operations shared by the job worker and synchronous API routes."""

    def __init__(
        self,
        settings: Settings,
        voices: VoiceStore,
        outputs: OutputStore,
        manager: ModelManager,
    ) -> None:
        self.settings = settings
        self.voices = voices
        self.outputs = outputs
        self.manager = manager

    def _ensure_ready(self) -> None:
        try:
            self.manager.ensure_ready()
        except ModelNotReadyError as exc:
            raise JobUnavailableError(str(exc)) from exc

    @staticmethod
    def _check_cancel(cancel_event: CancelEvent) -> None:
        if cancel_event.is_set():
            raise JobCancelled("Cancelled")

    @staticmethod
    def _progress(
        progress: ProgressFn | None,
        value: float,
        message: str,
    ) -> None:
        if progress is not None:
            progress(max(0.0, min(1.0, value)), message)

    def run_tts(
        self,
        req: TTSRequest,
        cancel_event: CancelEvent,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        self._ensure_ready()
        self._check_cancel(cancel_event)
        self._progress(progress, 0.03, "Preparing request")

        voice_meta: dict[str, Any] | None = None
        prompt: Any = None

        if req.mode == "voice":
            if not req.voice_id:
                raise JobValidationError(
                    "voice_id is required when mode is 'voice'"
                )
            try:
                voice_meta = self.voices.get_meta(req.voice_id)
            except KeyError as exc:
                raise JobValidationError("Voice not found") from exc

            prompt_path = self.voices.prompt_path(req.voice_id)
            if not prompt_path.is_file():
                raise JobValidationError(
                    "This voice has no trained prompt. Retrain it first."
                )
            try:
                prompt = self.manager.load_prompt(req.voice_id, prompt_path)
            except Exception as exc:
                raise JobValidationError(
                    f"Could not load the voice profile: {exc}"
                ) from exc
        elif req.mode == "design" and not req.instruct:
            raise JobValidationError(
                "instruct is required when mode is 'design'"
            )

        language = req.language or (
            voice_meta.get("language") if voice_meta else None
        )
        model_language = normalize_model_language(language)
        language_variant = req.language_variant or (
            language if language in PORTUGUESE_VARIANTS else None
        )

        # Fixed-duration requests cannot be split without changing semantics.
        chunks = (
            [req.text]
            if req.duration is not None
            else split_text_for_jobs(req.text)
        )

        generated: list[np.ndarray] = []
        sample_rate = self.manager.sample_rate
        total_elapsed = 0.0

        try:
            for index, chunk in enumerate(chunks, start=1):
                self._check_cancel(cancel_event)
                self._progress(
                    progress,
                    0.08 + 0.68 * ((index - 1) / max(1, len(chunks))),
                    f"Generating segment {index}/{len(chunks)}",
                )
                audio, sample_rate, elapsed = self.manager.generate(
                    text=chunk,
                    language=model_language,
                    voice_clone_prompt=prompt,
                    instruct=(
                        req.instruct
                        if req.mode == "design"
                        else (
                            req.style_instruct
                            if req.mode == "voice"
                            else None
                        )
                    ),
                    speed=req.speed,
                    duration=req.duration,
                    num_step=req.num_step,
                    guidance_scale=req.guidance_scale,
                    denoise=req.denoise,
                    t_shift=req.t_shift,
                    position_temperature=req.position_temperature,
                    class_temperature=req.class_temperature,
                    layer_penalty_factor=req.layer_penalty_factor,
                    postprocess_output=req.postprocess_output,
                    pad_duration=req.pad_duration,
                    fade_duration=req.fade_duration,
                    audio_chunk_duration=req.audio_chunk_duration,
                    audio_chunk_threshold=req.audio_chunk_threshold,
                    normalize_text=req.normalize_text,
                    seed=req.seed if index == 1 else None,
                )
                total_elapsed += elapsed
                self._check_cancel(cancel_event)

                if generated:
                    generated.append(
                        np.zeros(int(sample_rate * 0.06), dtype=np.float32)
                    )
                generated.append(audio)
        except ModelNotReadyError as exc:
            raise JobUnavailableError(str(exc)) from exc

        if not generated:
            raise JobValidationError("No audio was generated")

        audio = (
            np.concatenate(generated)
            if len(generated) > 1
            else generated[0]
        )
        duration = len(audio) / sample_rate if sample_rate else 0.0

        self._progress(progress, 0.82, "Encoding audio")
        self._check_cancel(cancel_event)
        try:
            data = encode_audio(audio, sample_rate, req.response_format)
        except Exception as exc:
            raise RuntimeError(f"Audio encoding failed: {exc}") from exc

        self._check_cancel(cancel_event)
        meta = {
            "text": req.text,
            "text_preview": req.text[:180],
            "mode": req.mode,
            "voice_id": req.voice_id if req.mode == "voice" else None,
            "voice_name": voice_meta.get("name") if voice_meta else None,
            "instruct": req.instruct if req.mode == "design" else None,
            "style_instruct": (
                req.style_instruct if req.mode == "voice" else None
            ),
            "language": language,
            "language_variant": language_variant,
            "seed": req.seed,
            "duration_seconds": round(duration, 3),
            "generation_seconds": round(total_elapsed, 3),
            "rtf": round(total_elapsed / duration, 4) if duration > 0 else None,
            "created_at": utc_now(),
        }
        self._progress(progress, 0.94, "Saving audio")
        meta = self.outputs.save(data, req.response_format, meta)
        meta["output_id"] = meta["id"]
        if cancel_event.is_set():
            try:
                self.outputs.delete(meta["id"])
            except Exception:
                pass
            raise JobCancelled("Cancelled")
        self._progress(progress, 1.0, "Completed")
        return meta

    def train_voice(
        self,
        *,
        name: str,
        language: str | None,
        transcript: str | None,
        transcript_provided: bool,
        audio_path: Path | None,
        voice_id: str | None,
        preprocess_prompt: bool = True,
        cancel_event: CancelEvent,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        self._ensure_ready()
        self._check_cancel(cancel_event)

        created = voice_id is None
        voice_dir: Path | None = None
        temp_wav: Path | None = None
        temp_prompt: Path | None = None

        try:
            if created:
                if audio_path is None:
                    raise JobValidationError(
                        "A reference audio file is required"
                    )
                voice_id, voice_dir = self.voices.create()
                ref_path = self.voices.reference_path(voice_id)
                candidate_ref = ref_path
                self._progress(progress, 0.1, "Decoding reference audio")
                try:
                    convert_to_wav(audio_path, ref_path)
                    duration = probe_duration(ref_path)
                except AudioConversionError as exc:
                    raise JobValidationError(
                        f"Could not decode the reference audio: {exc}"
                    ) from exc
                transcript_clean = (transcript or "").strip() or None
                language_value = (language or "").strip() or None
                existing_meta: dict[str, Any] | None = None
            else:
                try:
                    existing_meta = self.voices.get_meta(voice_id)
                except KeyError as exc:
                    raise JobValidationError("Voice not found") from exc

                voice_dir = self.voices._dir(voice_id)
                ref_path = self.voices.reference_path(voice_id)
                candidate_ref = ref_path

                if audio_path is not None:
                    temp_wav = voice_dir / "reference.new.wav"
                    self._progress(
                        progress, 0.1, "Decoding new reference audio"
                    )
                    try:
                        convert_to_wav(audio_path, temp_wav)
                        duration = probe_duration(temp_wav)
                    except AudioConversionError as exc:
                        raise JobValidationError(
                            f"Could not decode the reference audio: {exc}"
                        ) from exc
                    candidate_ref = temp_wav
                else:
                    self._progress(progress, 0.1, "Checking reference audio")
                    try:
                        duration = probe_duration(ref_path)
                    except AudioConversionError as exc:
                        raise JobValidationError(
                            f"Could not read the reference audio: {exc}"
                        ) from exc

                if transcript_provided:
                    transcript_clean = (transcript or "").strip() or None
                else:
                    transcript_clean = existing_meta.get("transcript") or None

                language_value = (
                    (language or "").strip() or None
                    if language is not None
                    else existing_meta.get("language")
                )

            self._check_cancel(cancel_event)
            if duration < self.settings.min_voice_seconds:
                raise JobValidationError(
                    f"Reference audio is too short ({duration:.1f}s). "
                    f"Use at least {self.settings.min_voice_seconds:.0f}s; "
                    "3-10s is ideal."
                )
            if duration > self.settings.max_voice_seconds:
                raise JobValidationError(
                    f"Reference audio is too long ({duration:.1f}s). "
                    f"Trim it to {self.settings.max_voice_seconds:.0f}s or "
                    "less; 3-10s is ideal."
                )

            self._progress(progress, 0.35, "Encoding the voice prompt")
            prompt = self.manager.create_prompt(
                str(candidate_ref),
                transcript_clean,
                preprocess_prompt=preprocess_prompt,
            )
            self._check_cancel(cancel_event)
            ref_text = (
                getattr(prompt, "ref_text", None) or transcript_clean or ""
            ).strip()

            if created:
                prompt_path = self.voices.prompt_path(voice_id)
                self._progress(progress, 0.75, "Saving the voice prompt")
                prompt.save(str(prompt_path))
                self._check_cancel(cancel_event)
            else:
                # Stage both files, then swap them only after cancellation is
                # ruled out. The previous profile stays consistent on cancel.
                prompt_path = self.voices.prompt_path(voice_id)
                temp_prompt = voice_dir / "prompt.new.pt"
                self._progress(progress, 0.75, "Saving the voice prompt")
                prompt.save(str(temp_prompt))
                self._check_cancel(cancel_event)
                if candidate_ref != ref_path:
                    candidate_ref.replace(ref_path)
                    temp_wav = None
                temp_prompt.replace(prompt_path)
                temp_prompt = None

            now = utc_now()
            if created:
                meta = {
                    "id": voice_id,
                    "name": name,
                    "language": language_value,
                    "transcript": ref_text or None,
                    "duration_seconds": round(duration, 3),
                    "sample_rate": 24_000,
                    "created_at": now,
                    "updated_at": now,
                    "has_preview": False,
                    "preview_updated_at": None,
                    "reference_filename": "reference.wav",
                    "prompt_filename": "prompt.pt",
                }
            else:
                meta = existing_meta or {}
                meta.update(
                    {
                        "name": name or meta.get("name"),
                        "language": language_value,
                        "transcript": ref_text or None,
                        "duration_seconds": round(duration, 3),
                        "updated_at": now,
                        "has_preview": False,
                        "preview_updated_at": None,
                    }
                )
                self.voices.preview_path(voice_id).unlink(missing_ok=True)

            self._progress(progress, 0.92, "Saving voice metadata")
            self.voices.save_meta(voice_id, meta)
            self.manager.invalidate_voice(voice_id)
            self._progress(progress, 1.0, "Completed")
            return meta
        except Exception:
            if created and voice_id is not None:
                self.voices.delete(voice_id)
            raise
        finally:
            if temp_wav is not None:
                temp_wav.unlink(missing_ok=True)
            if temp_prompt is not None:
                temp_prompt.unlink(missing_ok=True)

    def run_batch_tts(
        self,
        req: BatchTTSRequest,
        cancel_event: CancelEvent,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        total = len(req.texts)
        items: list[dict[str, Any]] = []
        for index, text in enumerate(req.texts):
            self._check_cancel(cancel_event)
            item = req.to_tts_request(text)
            item_progress = (
                None
                if progress is None
                else (
                    lambda value, message, index=index: progress(
                        (index + value) / total,
                        f"Item {index + 1}/{total}: {message}",
                    )
                )
            )
            items.append(
                self.run_tts(item, cancel_event, item_progress)
            )
        self._progress(progress, 1.0, "Completed")
        return {"items": items, "count": len(items)}

    def transcribe_audio(
        self,
        audio_path: Path,
        cancel_event: CancelEvent,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        self._ensure_ready()
        self._check_cancel(cancel_event)
        self._progress(progress, 0.1, "Loading ASR")
        text = self.manager.transcribe(str(audio_path))
        self._check_cancel(cancel_event)
        self._progress(progress, 1.0, "Completed")
        return {
            "text": text,
            "filename": audio_path.name,
        }

    def generate_preview(
        self,
        *,
        voice_id: str,
        text: str | None,
        cancel_event: CancelEvent,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        self._ensure_ready()
        self._check_cancel(cancel_event)

        try:
            meta = self.voices.get_meta(voice_id)
        except KeyError as exc:
            raise JobValidationError("Voice not found") from exc

        prompt_path = self.voices.prompt_path(voice_id)
        if not prompt_path.is_file():
            raise JobValidationError(
                "This voice has no trained prompt. Retrain it first."
            )

        try:
            prompt = self.manager.load_prompt(voice_id, prompt_path)
        except Exception as exc:
            raise JobValidationError(
                f"Could not load the voice profile: {exc}"
            ) from exc

        profile_language = meta.get("language")
        preview_text = (
            text
            or preview_text_for_language(
                profile_language,
                self.settings.preview_text,
            )
        ).strip()
        self._progress(progress, 0.15, "Generating preview")
        try:
            audio, sample_rate, elapsed = self.manager.generate(
                text=preview_text,
                language=normalize_model_language(profile_language),
                voice_clone_prompt=prompt,
                num_step=16,
            )
        except ModelNotReadyError as exc:
            raise JobUnavailableError(str(exc)) from exc

        self._check_cancel(cancel_event)
        preview_path = self.voices.preview_path(voice_id)
        temp_preview = preview_path.with_name("preview.new.wav")
        self._progress(progress, 0.8, "Saving preview")
        write_wav(temp_preview, audio, sample_rate)
        if cancel_event.is_set():
            temp_preview.unlink(missing_ok=True)
            raise JobCancelled("Cancelled")
        temp_preview.replace(preview_path)
        meta["has_preview"] = True
        meta["preview_updated_at"] = utc_now()
        self.voices.save_meta(voice_id, meta)
        self._progress(progress, 1.0, "Completed")
        return {
            "voice_id": voice_id,
            "voice_name": meta.get("name"),
            "duration_seconds": round(
                len(audio) / sample_rate if sample_rate else 0.0, 3
            ),
            "generation_seconds": round(elapsed, 3),
            "format": "wav",
            "preview_updated_at": meta["preview_updated_at"],
        }

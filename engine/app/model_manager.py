from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from .config import Settings

logger = logging.getLogger(__name__)


class ModelNotReadyError(RuntimeError):
    def __init__(self, message: str, status: str = "loading") -> None:
        super().__init__(message)
        self.status = status


class ModelManager:
    """Owns the single OmniVoice model instance and serializes inference."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model: Any = None
        self.status = "loading"
        self.status_message = "Starting OmniVoice"
        self.error: str | None = None
        self.device = settings.device
        self.sample_rate = 24_000
        self.started_at = time.time()
        self.load_started_at: float | None = None
        self.loaded_at: float | None = None

        self._torch: Any = None
        self._thread: threading.Thread | None = None
        self._model_lock = threading.RLock()
        self._cache_lock = threading.Lock()
        self._prompt_cache: dict[str, tuple[float, Any]] = {}

    @property
    def model_loaded(self) -> bool:
        return self.model is not None

    @property
    def asr_loaded(self) -> bool:
        return bool(self.model is not None and getattr(self.model, "_asr_pipe", None))

    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self.started_at, 1)

    @property
    def load_seconds(self) -> float | None:
        if self.load_started_at is None:
            return None
        end = self.loaded_at or time.time()
        return round(end - self.load_started_at, 1)

    def start_loading(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._load,
            name="omnivoice-loader",
            daemon=True,
        )
        self._thread.start()

    def reload(self) -> None:
        if self.status == "loading":
            return
        with self._model_lock:
            self.model = None
            self._prompt_cache.clear()
            if self._torch is not None:
                try:
                    if self._torch.cuda.is_available():
                        self._torch.cuda.empty_cache()
                except Exception:
                    pass
            self.status = "loading"
            self.status_message = "Reloading OmniVoice model"
            self.error = None
            self.loaded_at = None
        self.start_loading()

    def ensure_ready(self) -> None:
        if self.status == "error":
            raise ModelNotReadyError(
                self.error or "The model failed to load", status="error"
            )
        if self.model is None:
            raise ModelNotReadyError(
                "The model is still loading. Please wait for warm-up to finish.",
                status="loading",
            )

    def _resolve_device(self, torch: Any) -> str:
        requested = (self.settings.device or "auto").strip()
        if requested and requested.lower() != "auto":
            return requested
        if torch.cuda.is_available():
            return "cuda:0"
        try:
            if torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        try:
            if hasattr(torch, "xpu") and torch.xpu.is_available():
                return "xpu"
        except Exception:
            pass
        return "cpu"

    def _load(self) -> None:
        self.status = "loading"
        self.status_message = (
            "Loading OmniVoice model weights. The first run downloads several GB."
        )
        self.error = None
        self.load_started_at = time.time()
        self.loaded_at = None

        try:
            import torch
            from omnivoice import OmniVoice

            self._torch = torch
            device = self._resolve_device(torch)
            dtype = (
                torch.float16
                if str(device).startswith(("cuda", "xpu"))
                else torch.float32
            )

            logger.info(
                "Loading OmniVoice model %s on %s (%s)",
                self.settings.model_id,
                device,
                dtype,
            )
            model = OmniVoice.from_pretrained(
                self.settings.model_id,
                device_map=device,
                dtype=dtype,
                asr_model_name=self.settings.asr_model,
                asr_device=self.settings.asr_device,
                load_asr=self.settings.load_asr,
            )

            with self._model_lock:
                self.model = model
                self.device = str(getattr(model, "device", device))
                self.sample_rate = int(getattr(model, "sampling_rate", 24_000) or 24_000)
                self.status = "ok"
                self.status_message = "Model ready"
                self.loaded_at = time.time()

            logger.info(
                "OmniVoice ready on %s in %.1fs",
                self.device,
                self.load_seconds or 0.0,
            )
        except Exception as exc:
            logger.exception("Failed to load OmniVoice")
            with self._model_lock:
                self.model = None
                self.status = "error"
                self.status_message = "Model failed to load"
                self.error = str(exc)
                self.loaded_at = None

    def create_prompt(self, ref_audio: str, ref_text: str | None) -> Any:
        with self._model_lock:
            self.ensure_ready()
            return self.model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=ref_text or None,
                preprocess_prompt=True,
            )

    def load_prompt(self, voice_id: str, path: Path) -> Any:
        from omnivoice import VoiceClonePrompt

        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError as exc:
            raise FileNotFoundError("Voice prompt file is missing") from exc

        with self._cache_lock:
            cached = self._prompt_cache.get(voice_id)
            if cached is not None and cached[0] == mtime:
                return cached[1]

        prompt = VoiceClonePrompt.load(str(path))
        with self._cache_lock:
            self._prompt_cache[voice_id] = (mtime, prompt)
        return prompt

    def invalidate_voice(self, voice_id: str) -> None:
        with self._cache_lock:
            self._prompt_cache.pop(voice_id, None)

    def generate(
        self,
        *,
        text: str,
        language: str | None = None,
        voice_clone_prompt: Any = None,
        instruct: str | None = None,
        speed: float | None = 1.0,
        duration: float | None = None,
        num_step: int = 32,
        guidance_scale: float = 2.0,
        denoise: bool = True,
        postprocess_output: bool = True,
    ) -> tuple[Any, int, float]:
        with self._model_lock:
            self.ensure_ready()
            started = time.time()
            audios = self.model.generate(
                text=text,
                language=language or None,
                voice_clone_prompt=voice_clone_prompt,
                instruct=instruct or None,
                speed=speed,
                duration=duration,
                num_step=num_step,
                guidance_scale=guidance_scale,
                denoise=denoise,
                postprocess_output=postprocess_output,
                audio_chunk_duration=15.0,
                audio_chunk_threshold=30.0,
            )
            elapsed = time.time() - started
            return audios[0], self.sample_rate, elapsed

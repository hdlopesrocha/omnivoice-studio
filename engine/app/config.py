from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    model_id: str
    device: str
    asr_model: str
    asr_device: str | None
    load_asr: bool
    cors_origins: tuple[str, ...]
    max_input_chars: int
    max_upload_mb: int
    min_voice_seconds: float
    max_voice_seconds: float
    preview_text: str
    max_queue_size: int
    max_job_history: int
    app_version: str = "1.0.0"

    @property
    def voices_dir(self) -> Path:
        return self.data_dir / "voices"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", "/data")).expanduser(),
            model_id=os.getenv("OMNIVOICE_MODEL", "k2-fsa/OmniVoice").strip(),
            device=os.getenv("DEVICE", "auto").strip() or "auto",
            asr_model=os.getenv(
                "OMNIVOICE_ASR_MODEL", "openai/whisper-large-v3-turbo"
            ).strip(),
            asr_device=(os.getenv("OMNIVOICE_ASR_DEVICE") or "").strip() or None,
            load_asr=_env_bool("OMNIVOICE_LOAD_ASR", False),
            cors_origins=_env_list(
                "CORS_ORIGINS",
                (
                    "http://localhost:8088",
                    "http://127.0.0.1:8088",
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                ),
            ),
            max_input_chars=_env_int("MAX_INPUT_CHARS", 8000),
            max_upload_mb=_env_int("MAX_UPLOAD_MB", 50),
            min_voice_seconds=_env_float("MIN_VOICE_SECONDS", 1.0),
            max_voice_seconds=_env_float("MAX_VOICE_SECONDS", 30.0),
            preview_text=os.getenv(
                "OMNIVOICE_PREVIEW_TEXT",
                "Hello! This is a preview of my trained voice. "
                "I hope you like how it sounds.",
            ).strip(),
            max_queue_size=_env_int("MAX_QUEUE_SIZE", 50),
            max_job_history=_env_int("MAX_JOB_HISTORY", 200),
        )

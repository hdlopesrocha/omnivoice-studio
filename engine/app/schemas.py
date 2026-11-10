from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

AudioFormat = Literal["wav", "mp3", "flac"]
TTSMode = Literal["voice", "design", "auto"]


class GenerationParams(BaseModel):
    mode: TTSMode = "voice"
    voice_id: str | None = Field(None, max_length=32)
    instruct: str | None = Field(None, max_length=300)
    style_instruct: str | None = Field(None, max_length=300)
    language: str | None = Field(None, max_length=64)
    language_variant: str | None = Field(None, max_length=16)
    speed: float | None = Field(1.0, ge=0.25, le=4.0)
    duration: float | None = Field(None, ge=0.5, le=600.0)
    num_step: int = Field(32, ge=1, le=128)
    guidance_scale: float = Field(2.0, ge=0.0, le=20.0)
    denoise: bool = True
    t_shift: float = Field(0.1, ge=0.0, le=10.0)
    position_temperature: float = Field(5.0, ge=0.0, le=100.0)
    class_temperature: float = Field(0.0, ge=0.0, le=10.0)
    layer_penalty_factor: float = Field(5.0, ge=0.0, le=100.0)
    postprocess_output: bool = True
    pad_duration: float = Field(0.1, ge=0.0, le=5.0)
    fade_duration: float = Field(0.1, ge=0.0, le=5.0)
    audio_chunk_duration: float = Field(15.0, gt=0.0, le=120.0)
    audio_chunk_threshold: float = Field(30.0, ge=0.0, le=600.0)
    normalize_text: bool = False
    seed: int | None = Field(None, ge=0, le=4_294_967_295)
    response_format: AudioFormat = "wav"

    @field_validator(
        "instruct",
        "style_instruct",
        "language",
        "language_variant",
        "voice_id",
    )
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class TTSRequest(GenerationParams):
    text: str = Field(..., min_length=1, max_length=8000)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be empty")
        return value


class BatchTTSRequest(GenerationParams):
    texts: list[str] = Field(..., min_length=1, max_length=50)

    @field_validator("texts")
    @classmethod
    def _clean_texts(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if not value:
                raise ValueError("Batch items cannot be empty")
            if len(value) > 8000:
                raise ValueError("Batch items must be 8,000 characters or less")
            cleaned.append(value)
        if not cleaned:
            raise ValueError("At least one batch item is required")
        return cleaned

    def to_tts_request(self, text: str) -> TTSRequest:
        return TTSRequest(
            text=text,
            **self.model_dump(exclude={"texts"}),
        )


class VoiceRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty")
        return value


class OpenAISpeechRequest(BaseModel):
    model: str = "omnivoice"
    input: str = Field(..., min_length=1, max_length=8000)
    voice: str = Field("auto", max_length=300)
    response_format: AudioFormat = "wav"
    speed: float | None = Field(1.0, ge=0.25, le=4.0)
    language: str | None = Field(None, max_length=64)
    language_variant: str | None = Field(None, max_length=16)
    instruct: str | None = Field(None, max_length=300)
    style_instruct: str | None = Field(None, max_length=300)
    normalize_text: bool = False
    seed: int | None = Field(None, ge=0, le=4_294_967_295)

    @field_validator("input")
    @classmethod
    def _strip_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Input cannot be empty")
        return value

    @field_validator(
        "language",
        "language_variant",
        "instruct",
        "style_instruct",
        "voice",
    )
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

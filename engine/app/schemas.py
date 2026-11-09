from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

AudioFormat = Literal["wav", "mp3", "flac"]
TTSMode = Literal["voice", "design", "auto"]


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    mode: TTSMode = "voice"
    voice_id: str | None = Field(None, max_length=32)
    instruct: str | None = Field(None, max_length=300)
    language: str | None = Field(None, max_length=64)
    language_variant: str | None = Field(None, max_length=16)
    speed: float | None = Field(1.0, ge=0.25, le=4.0)
    duration: float | None = Field(None, ge=0.5, le=600.0)
    num_step: int = Field(32, ge=1, le=128)
    guidance_scale: float = Field(2.0, ge=0.0, le=20.0)
    denoise: bool = True
    postprocess_output: bool = True
    response_format: AudioFormat = "wav"

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be empty")
        return value

    @field_validator("instruct", "language", "language_variant", "voice_id")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


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

    @field_validator("input")
    @classmethod
    def _strip_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Input cannot be empty")
        return value

    @field_validator("language", "language_variant", "instruct", "voice")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VOICE_ID_RE = re.compile(r"^[0-9a-f]{12}$")
OUTPUT_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object in {path}")
    return payload


class VoiceStore:
    """Persistent storage for reusable voice profiles."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, voice_id: str) -> Path:
        if not VOICE_ID_RE.match(voice_id):
            raise KeyError("Voice not found")
        return self.root / voice_id

    def create(self) -> tuple[str, Path]:
        self.ensure()
        voice_id = uuid.uuid4().hex[:12]
        path = self.root / voice_id
        path.mkdir(parents=True, exist_ok=False)
        return voice_id, path

    def delete(self, voice_id: str) -> None:
        shutil.rmtree(self._dir(voice_id), ignore_errors=True)

    def exists(self, voice_id: str) -> bool:
        try:
            return self._dir(voice_id).is_dir()
        except KeyError:
            return False

    def meta_path(self, voice_id: str) -> Path:
        return self._dir(voice_id) / "meta.json"

    def reference_path(self, voice_id: str) -> Path:
        return self._dir(voice_id) / "reference.wav"

    def prompt_path(self, voice_id: str) -> Path:
        return self._dir(voice_id) / "prompt.pt"

    def preview_path(self, voice_id: str) -> Path:
        return self._dir(voice_id) / "preview.wav"

    def save_meta(self, voice_id: str, meta: dict[str, Any]) -> None:
        _write_json(self.meta_path(voice_id), meta)

    def get_meta(self, voice_id: str) -> dict[str, Any]:
        path = self.meta_path(voice_id)
        if not path.is_file():
            raise KeyError("Voice not found")
        return _read_json(path)

    def list_meta(self) -> list[dict[str, Any]]:
        self.ensure()
        voices: list[dict[str, Any]] = []
        for entry in self.root.iterdir():
            if not entry.is_dir() or not VOICE_ID_RE.match(entry.name):
                continue
            meta_file = entry / "meta.json"
            if not meta_file.is_file():
                continue
            try:
                meta = _read_json(meta_file)
            except Exception:
                continue
            if not meta.get("id"):
                meta["id"] = entry.name
            voices.append(meta)
        voices.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return voices


class OutputStore:
    """Persistent generation history."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, output_id: str) -> Path:
        if not OUTPUT_ID_RE.match(output_id):
            raise KeyError("Output not found")
        return self.root / f"{output_id}.json"

    def save(self, data: bytes, fmt: str, meta: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        output_id = uuid.uuid4().hex[:12]
        filename = f"{output_id}.{fmt}"
        (self.root / filename).write_bytes(data)

        payload = {
            **meta,
            "id": output_id,
            "filename": filename,
            "format": fmt,
            "size_bytes": len(data),
        }
        _write_json(self.root / f"{output_id}.json", payload)
        return payload

    def get_meta(self, output_id: str) -> dict[str, Any]:
        path = self._meta_path(output_id)
        if not path.is_file():
            raise KeyError("Output not found")
        return _read_json(path)

    def audio_path(self, meta: dict[str, Any]) -> Path:
        filename = meta.get("filename")
        if not filename or "/" in filename or "\\" in filename:
            raise KeyError("Output audio not found")
        path = self.root / filename
        if not path.is_file():
            raise KeyError("Output audio not found")
        return path

    def list_meta(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure()
        outputs: list[dict[str, Any]] = []
        for entry in self.root.glob("*.json"):
            try:
                meta = _read_json(entry)
                if self.audio_path(meta).is_file():
                    outputs.append(meta)
            except Exception:
                continue
        outputs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return outputs[: max(0, limit)]

    def delete(self, output_id: str) -> None:
        meta = self.get_meta(output_id)
        try:
            self.audio_path(meta).unlink(missing_ok=True)
        except KeyError:
            pass
        self._meta_path(output_id).unlink(missing_ok=True)

    def count(self) -> int:
        return len(list(self.root.glob("*.json"))) if self.root.exists() else 0

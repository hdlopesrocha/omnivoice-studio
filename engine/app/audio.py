from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24_000
MIME_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
}
SUPPORTED_FORMATS = tuple(MIME_TYPES)


class AudioConversionError(RuntimeError):
    """Raised when ffmpeg cannot decode or encode an audio file."""


def _run_ffmpeg(cmd: list[str], timeout: int = 180) -> None:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioConversionError("Audio conversion timed out") from exc

    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioConversionError(detail or "ffmpeg failed")


def convert_to_wav(src: Path, dst: Path, sample_rate: int = SAMPLE_RATE) -> None:
    """Decode any ffmpeg-supported input into mono 16-bit PCM WAV."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(dst),
        ]
    )
    if not dst.exists() or dst.stat().st_size == 0:
        raise AudioConversionError("Converted audio file is empty")


def convert_wav_to(src: Path, dst: Path, fmt: str) -> None:
    """Convert a WAV file to mp3/flac/wav using ffmpeg."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "wav":
        if src != dst:
            dst.write_bytes(src.read_bytes())
        return

    codec = ["-c:a", "libmp3lame", "-b:a", "192k"] if fmt == "mp3" else ["-c:a", "flac"]
    _run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-vn",
            *codec,
            str(dst),
        ]
    )


def probe_duration(path: Path) -> float:
    """Return duration in seconds, using soundfile with an ffprobe fallback."""
    try:
        info = sf.info(str(path))
        return float(info.duration)
    except Exception:
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            return float(proc.stdout.decode().strip())
        except Exception as exc:
            raise AudioConversionError("Could not read audio duration") from exc


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sample_rate, format="WAV", subtype="PCM_16")


def encode_audio(audio: np.ndarray, sample_rate: int, fmt: str) -> bytes:
    """Encode a float waveform into the requested container."""
    fmt = fmt.lower()
    if fmt not in MIME_TYPES:
        raise ValueError(f"Unsupported audio format: {fmt}")

    if fmt == "wav":
        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    if fmt == "flac":
        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="FLAC", subtype="PCM_16")
        return buf.getvalue()

    # MP3 is not supported by libsndfile everywhere; use ffmpeg.
    with tempfile.TemporaryDirectory(prefix="omnivoice-encode-") as tmp:
        wav_path = Path(tmp) / "audio.wav"
        mp3_path = Path(tmp) / "audio.mp3"
        sf.write(wav_path, audio, sample_rate, format="WAV", subtype="PCM_16")
        convert_wav_to(wav_path, mp3_path, "mp3")
        return mp3_path.read_bytes()

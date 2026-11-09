from __future__ import annotations

import io
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# Configure the data directory before importing the app.
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="omnivoice-studio-test-"))
os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["MAX_UPLOAD_MB"] = "5"
os.environ["MIN_VOICE_SECONDS"] = "1"
os.environ["MAX_VOICE_SECONDS"] = "30"
os.environ["MAX_QUEUE_SIZE"] = "10"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as main_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class FakePrompt:
    def __init__(self, ref_text: str = "hello from the reference") -> None:
        self.ref_text = ref_text

    def save(self, path: str) -> None:
        Path(path).write_bytes(b"fake-prompt")


class FakeManager:
    status = "ok"
    status_message = "Model ready"
    error = None
    model_loaded = True
    device = "cpu"
    sample_rate = 24_000
    asr_loaded = False
    load_seconds = 0.1
    uptime_seconds = 1.0

    def __init__(self) -> None:
        self.delay = 0.0
        self.languages: list[str | None] = []

    def start_loading(self) -> None:
        return None

    def reload(self) -> None:
        return None

    def ensure_ready(self) -> None:
        return None

    def create_prompt(self, ref_audio: str, ref_text: str | None) -> FakePrompt:
        return FakePrompt(ref_text or "auto transcribed reference")

    def load_prompt(self, voice_id: str, path: Path) -> FakePrompt:
        return FakePrompt("loaded prompt")

    def invalidate_voice(self, voice_id: str) -> None:
        return None

    def generate(
        self,
        *,
        text: str,
        language: str | None = None,
        voice_clone_prompt=None,
        instruct: str | None = None,
        speed: float | None = 1.0,
        duration: float | None = None,
        num_step: int = 32,
        guidance_scale: float = 2.0,
        denoise: bool = True,
        postprocess_output: bool = True,
    ):
        if self.delay:
            time.sleep(self.delay)
        self.languages.append(language)
        sample_rate = 24_000
        seconds = min(1.0, max(0.25, len(text) / 100))
        timeline = np.linspace(
            0,
            seconds,
            int(sample_rate * seconds),
            endpoint=False,
            dtype=np.float32,
        )
        audio = (0.1 * np.sin(2 * np.pi * 220 * timeline)).astype(np.float32)
        return audio, sample_rate, 0.05


def wav_bytes(seconds: float = 2.0) -> bytes:
    sample_rate = 24_000
    timeline = np.linspace(
        0,
        seconds,
        int(sample_rate * seconds),
        endpoint=False,
        dtype=np.float32,
    )
    audio = (0.15 * np.sin(2 * np.pi * 180 * timeline)).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    fake = FakeManager()
    monkeypatch.setattr(main_module, "manager", fake)
    monkeypatch.setattr(main_module.runtime, "manager", fake)
    with TestClient(main_module.app) as test_client:
        yield test_client


def create_voice(
    client: TestClient,
    name: str = "Test Voice",
    language: str = "en",
) -> dict:
    response = client.post(
        "/api/voices",
        data={
            "name": name,
            "transcript": "this is the reference transcript",
            "language": language,
            "consent": "true",
        },
        files={"audio": ("sample.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_job(
    client: TestClient,
    job_id: str,
    *,
    timeout: float = 10.0,
) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Job did not finish: {last}")


def test_health_and_languages(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["model_loaded"] is True

    languages = client.get("/api/languages")
    assert languages.status_code == 200
    payload = languages.json()
    assert payload["count"] >= 600
    assert any(item["id"] == "en" for item in payload["languages"])


def test_voice_training_preview_and_tts(client: TestClient):
    voice = create_voice(client)
    voice_id = voice["id"]
    assert voice["transcript"] == "this is the reference transcript"

    listing = client.get("/api/voices")
    assert listing.status_code == 200
    assert any(item["id"] == voice_id for item in listing.json()["voices"])

    reference = client.get(f"/api/voices/{voice_id}/reference")
    assert reference.status_code == 200
    assert reference.headers["content-type"].startswith("audio/wav")

    preview = client.post(f"/api/voices/{voice_id}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"].startswith("audio/wav")

    cached_preview = client.get(f"/api/voices/{voice_id}/preview")
    assert cached_preview.status_code == 200

    tts = client.post(
        "/api/tts",
        json={
            "text": "Hello from the test suite.",
            "mode": "voice",
            "voice_id": voice_id,
            "language": "en",
            "response_format": "wav",
        },
    )
    assert tts.status_code == 200, tts.text
    assert tts.headers["content-type"].startswith("audio/wav")
    output_id = tts.headers["x-output-id"]
    assert output_id

    history = client.get("/api/outputs")
    assert history.status_code == 200
    assert any(item["id"] == output_id for item in history.json()["outputs"])

    audio = client.get(f"/api/outputs/{output_id}")
    assert audio.status_code == 200
    assert len(audio.content) > 1000

    download = client.get(f"/api/outputs/{output_id}?download=1")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]

    assert client.delete(f"/api/outputs/{output_id}").status_code == 200
    assert client.get(f"/api/outputs/{output_id}").status_code == 404


def test_design_mode_and_openai_shim(client: TestClient):
    design = client.post(
        "/api/tts",
        json={
            "text": "A designed voice.",
            "mode": "design",
            "instruct": "female, low pitch, british accent",
            "response_format": "wav",
        },
    )
    assert design.status_code == 200, design.text

    voice = create_voice(client, name="OpenAI Voice")
    openai = client.post(
        "/api/v1/audio/speech",
        json={
            "model": "omnivoice",
            "input": "Hello from the OpenAI compatible endpoint.",
            "voice": voice["name"],
            "response_format": "wav",
        },
    )
    assert openai.status_code == 200, openai.text
    assert openai.headers["content-type"].startswith("audio/wav")


def test_retrain_and_delete(client: TestClient):
    voice = create_voice(client, name="Retrain Voice")
    voice_id = voice["id"]

    retrain = client.post(
        f"/api/voices/{voice_id}/retrain",
        data={
            "transcript": "a brand new transcript",
            "language": "fr",
            "consent": "true",
        },
    )
    assert retrain.status_code == 200, retrain.text
    assert retrain.json()["transcript"] == "a brand new transcript"
    assert retrain.json()["language"] == "fr"

    rename = client.patch(
        f"/api/voices/{voice_id}", json={"name": "Renamed Voice"}
    )
    assert rename.status_code == 200
    assert rename.json()["name"] == "Renamed Voice"

    assert client.delete(f"/api/voices/{voice_id}").status_code == 200
    assert client.get(f"/api/voices/{voice_id}").status_code == 404


def test_validation_errors(client: TestClient):
    missing_voice = client.post(
        "/api/tts",
        json={"text": "Hello", "mode": "voice"},
    )
    assert missing_voice.status_code == 400

    empty_text = client.post(
        "/api/tts",
        json={"text": "   ", "mode": "auto"},
    )
    assert empty_text.status_code == 422


def test_job_submit_poll_audio_and_delete(client: TestClient):
    response = client.post(
        "/api/jobs/tts",
        json={
            "text": "A queued job.",
            "mode": "auto",
            "response_format": "wav",
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] in {"queued", "running"}
    assert job["can_cancel"] in {True, False}

    finished = wait_for_job(client, job["id"])
    assert finished["status"] == "completed", finished
    assert finished["result"]["output_id"]
    assert finished["has_audio"] is True

    audio = client.get(f"/api/jobs/{job['id']}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")

    listing = client.get("/api/jobs")
    assert listing.status_code == 200
    assert any(item["id"] == job["id"] for item in listing.json()["jobs"])

    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_cancel_queued_and_running_jobs(client: TestClient):
    fake = main_module.runtime.manager
    assert isinstance(fake, FakeManager)
    fake.delay = 0.7

    first = client.post(
        "/api/jobs/tts",
        json={"text": "First slow job.", "mode": "auto"},
    ).json()
    deadline = time.time() + 5
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{first['id']}").json()
        if state["status"] == "running":
            break
        time.sleep(0.02)
    assert state["status"] == "running"

    second = client.post(
        "/api/jobs/tts",
        json={"text": "Second queued job.", "mode": "auto"},
    ).json()
    assert second["status"] == "queued"
    assert second["queue_position"] == 1

    cancelled = client.post(f"/api/jobs/{second['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    running_cancel = client.post(f"/api/jobs/{first['id']}/cancel")
    assert running_cancel.status_code == 200
    assert running_cancel.json()["status"] in {"cancelling", "cancelled"}

    finished = wait_for_job(client, first["id"], timeout=10)
    assert finished["status"] == "cancelled", finished

    fake.delay = 0.0


def test_portuguese_variants_require_matching_voice(client: TestClient):
    fake = main_module.runtime.manager
    assert isinstance(fake, FakeManager)
    fake.languages.clear()

    voice = create_voice(
        client,
        name="Portugal Voice",
        language="pt-PT",
    )
    voice_id = voice["id"]
    assert voice["language"] == "pt-PT"

    response = client.post(
        "/api/tts",
        json={
            "text": "Bom dia. Este teste é em português de Portugal.",
            "mode": "voice",
            "voice_id": voice_id,
            "language": "pt",
            "language_variant": "pt-PT",
            "response_format": "wav",
        },
    )
    assert response.status_code == 200, response.text
    assert fake.languages[-1] == "pt"
    output_id = response.headers["x-output-id"]
    history = client.get("/api/outputs").json()["outputs"]
    output = next(item for item in history if item["id"] == output_id)
    assert output["language_variant"] == "pt-PT"

    auto = client.post(
        "/api/tts",
        json={
            "text": "Bom dia.",
            "mode": "auto",
            "language": "pt",
            "language_variant": "pt-PT",
        },
    )
    assert auto.status_code == 400

    wrong_voice = client.post(
        "/api/tts",
        json={
            "text": "Bom dia.",
            "mode": "voice",
            "voice_id": voice_id,
            "language": "pt",
            "language_variant": "pt-BR",
        },
    )
    assert wrong_voice.status_code == 400

    direct_variant = client.post(
        "/api/tts",
        json={
            "text": "Bom dia.",
            "mode": "voice",
            "voice_id": voice_id,
            "language": "pt-PT",
        },
    )
    assert direct_variant.status_code == 200, direct_variant.text
    assert fake.languages[-1] == "pt"


def test_job_voice_training_and_preview(client: TestClient):
    response = client.post(
        "/api/jobs/voices",
        data={
            "name": "Queued Voice",
            "transcript": "queued training transcript",
            "language": "en",
            "consent": "true",
        },
        files={"audio": ("sample.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    finished = wait_for_job(client, job["id"])
    assert finished["status"] == "completed", finished
    voice_id = finished["result"]["id"]
    assert voice_id

    preview = client.post(f"/api/jobs/voices/{voice_id}/preview")
    assert preview.status_code == 202, preview.text
    preview_job = preview.json()
    preview_finished = wait_for_job(client, preview_job["id"])
    assert preview_finished["status"] == "completed", preview_finished
    assert preview_finished["has_audio"] is True

    audio = client.get(f"/api/jobs/{preview_job['id']}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")

    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert client.delete(f"/api/jobs/{preview_job['id']}").status_code == 200
    assert client.delete(f"/api/voices/{voice_id}").status_code == 200


def test_cancel_queued_endpoint(client: TestClient):
    fake = main_module.runtime.manager
    assert isinstance(fake, FakeManager)
    fake.delay = 0.5

    first = client.post(
        "/api/jobs/tts",
        json={"text": "Hold the worker.", "mode": "auto"},
    ).json()
    deadline = time.time() + 5
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{first['id']}").json()
        if state["status"] == "running":
            break
        time.sleep(0.02)

    queued_ids = []
    for index in range(2):
        queued = client.post(
            "/api/jobs/tts",
            json={"text": f"Queued {index}.", "mode": "auto"},
        ).json()
        queued_ids.append(queued["id"])

    result = client.post("/api/jobs/cancel-queued")
    assert result.status_code == 200
    assert result.json()["cancelled"] >= 1

    for job_id in queued_ids:
        state = client.get(f"/api/jobs/{job_id}").json()
        assert state["status"] == "cancelled"

    client.post(f"/api/jobs/{first['id']}/cancel")
    wait_for_job(client, first["id"], timeout=10)
    fake.delay = 0.0

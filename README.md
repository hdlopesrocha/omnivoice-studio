# OmniVoice Studio

A local-first, Dockerized text-to-speech studio built around
[OmniVoice](https://github.com/k2-fsa/OmniVoice). It ships a Vue 3 frontend, a
FastAPI engine, reusable voice profiles, voice design, and persistent history.
Everything runs on your machine — no hosted API, no telemetry, and no audio
leaving your Docker volume.

```text
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  Vue 3 + Vite + TypeScript   │  /api  │  FastAPI engine              │
│  nginx on :8088              │ ─────▶ │  OmniVoice + Whisper (opt.)  │
└──────────────────────────────┘        │  :8000                       │
                                        └──────────────┬───────────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │  Docker volume      │
                                            │  voices/ outputs/   │
                                            │  Hugging Face cache │
                                            └─────────────────────┘
```

## What it does

- **Text to speech** with OmniVoice across 600+ languages.
- **Train a voice** from a 3–10 second reference clip. OmniVoice is zero-shot,
  so “training” here means encoding the clip into a reusable voice-clone prompt
  (no model-weight fine-tuning). The prompt is cached on disk and reused.
- **Voice design** from attributes such as `female, low pitch, british accent`.
- **Optional Whisper auto-transcription** when you leave the reference
  transcript blank.
- **Persistent history** of every generation, with play/download/delete.
- **Cancellable job queue**: queue multiple generations, see progress, cancel
  queued jobs instantly, and stop running jobs at the next safe checkpoint.
- **CPU and NVIDIA GPU** stacks, selected automatically by the Makefile.
- **Local-only by default**: ports bind to `127.0.0.1`, and all data lives in a
  named Docker volume.

## Requirements

- Docker Engine 24+ with Docker Compose v2
- ~8 GB RAM for the CPU stack (more is better)
- Optional NVIDIA GPU: recent driver + NVIDIA Container Toolkit
- ~12–15 GB free disk for the engine image, dependencies, and model weights
- Python 3 on the host for the Makefile helpers (`make wait`, `make say`, JSON formatting)
- For the host-side dev server: Node.js 20+ (only needed for `make dev`)

## Quick start

```bash
git clone https://github.com/your-name/omnivoice-studio.git
cd omnivoice-studio

make up        # builds the CPU or GPU stack automatically
make wait      # waits for the model to finish loading
open http://localhost:8088
```

The first `make up` also builds a large engine image (PyTorch, ffmpeg, and the
OmniVoice dependencies), so it can take a while on a slow connection. The first
boot then downloads the OmniVoice checkpoint (several GB) into the
`omnivoice-studio_omnivoice-data` volume. The UI stays usable while the engine
warms up and unlocks when the status pill turns green.

Force a stack if auto-detection is not what you want:

```bash
make up-gpu
make up-cpu
```

Stop everything without deleting data:

```bash
make down
```

Delete containers **and** all voices, history, and cached models:

```bash
make clean
```

## Train a voice

1. Open **Voices → Train voice**.
2. Record 3–10 seconds (up to 20s) or upload a WAV/MP3/M4A/OGG/WebM/FLAC file.
3. Optionally type the exact transcript. Leave it blank to auto-transcribe with
   Whisper; typing it is faster and usually improves cloning.
4. Pick the language spoken in the clip.
5. Confirm you have permission to use the voice and press **Train voice**.

The engine converts the clip to 24 kHz mono, creates an OmniVoice
`VoiceClonePrompt`, and stores it under `/data/voices/<id>/`:

```text
/data/voices/<id>/
├── meta.json        # name, language, transcript, duration, timestamps
├── reference.wav    # normalized 24 kHz mono reference
├── prompt.pt        # cached OmniVoice voice-clone prompt
└── preview.wav      # optional generated preview
```

You can also train from the CLI:

```bash
make voice NAME=Alice AUDIO=./alice.wav \
  TRANSCRIPT="The exact words spoken in the clip." LANG=en
```

> **Training vs. fine-tuning:** this app deliberately implements zero-shot
> voice enrollment, not gradient fine-tuning. A 3–10 second sample is enough
> because the model is not modified. If you need LoRA fine-tuning, OmniVoice
> publishes a separate GPU-heavy recipe upstream:
> <https://github.com/k2-fsa/OmniVoice/blob/master/docs/lora_finetuning.md>.

## Portuguese: Portugal vs. Brazil

OmniVoice exposes a single `pt` model language. The app adds `pt-PT` and
`pt-BR` as **profile tags**, because the model cannot select a Portuguese
variant from a language code alone — the **reference clip controls the accent**.

- **Portuguese (Portugal)**: train or tag a voice profile using a European
  Portuguese reference clip, then select that profile and
  `Portuguese (Portugal)` in Studio.
- **Portuguese (Brazil)**: same idea with a Brazilian reference clip and the
  `Portuguese (Brazil)` tag.
- Auto voice and voice design are blocked for these variants because they
  cannot guarantee the accent.
- To tag an existing profile, open **Voices → Retrain**, choose the Portuguese
  variant, keep the existing reference clip, and submit.

API clients can send `language=pt` plus `language_variant=pt-PT` (recommended
for compatibility) or `language=pt-PT` on the updated engine.

## Jobs and cancellation

Every long-running operation — TTS, voice training, retraining, and previews —
goes through one local FIFO worker. The **Jobs** page shows queue position,
progress, elapsed time, and results.

- **Queued jobs** cancel immediately.
- **Running TTS jobs** are split at sentence/paragraph boundaries (up to ~420
  characters per model call), so cancellation takes effect after the current
  segment finishes.
- **Running voice jobs** stop after the current conversion or prompt-encoding
  step. A single short TTS segment cannot be preempted mid-inference; the
  cancellation is applied as soon as that model call returns.
- Job records live in the engine process for the current session. Generated
  audio, trained voices, and previews remain in the data volume after a restart.

```bash
make jobs                    # list queued/running/recent jobs
make job JOB_ID=abc123def456 # inspect one job
make cancel JOB_ID=abc123def456
make cancel-queued           # cancel every queued job
make job-audio JOB_ID=abc123def456 OUT=result.wav
```

`make say` and the synchronous API still work: they enqueue a job and wait for
it, so they appear in the same queue and can be cancelled from another terminal
or from the Jobs page.

## Synthesize from the CLI

```bash
# Auto voice
make say TEXT="Hello from my local OmniVoice." OUT=hello.wav

# A trained voice
make say TEXT="This is Alice speaking." VOICE_ID=abc123def456 OUT=alice.wav

# Voice design
make say TEXT="A designed voice." MODE=design \
  INSTRUCT="female, low pitch, british accent" OUT=design.wav
```

## Make targets

| Target | What it does |
| --- | --- |
| `make up` | Build and start the stack; auto-detects an NVIDIA GPU |
| `make start` | Start already-built containers |
| `make up-gpu` / `make up-cpu` | Force an accelerator |
| `make build` | Build images for the detected accelerator |
| `make wait` | Poll the API until the model is loaded |
| `make logs` / `make logs-engine` | Follow logs |
| `make status` / `make info` | Print engine health/capabilities |
| `make voices` / `make outputs` | List trained voices/history |
| `make voice NAME=… AUDIO=…` | Train a profile from the CLI |
| `make say TEXT=…` | Generate speech from the CLI |
| `make preview VOICE_ID=…` | Generate a voice preview |
| `make jobs` / `make job JOB_ID=…` | List or inspect jobs |
| `make cancel JOB_ID=…` | Cancel a queued/running job |
| `make cancel-queued` | Cancel every queued job |
| `make job-audio JOB_ID=… OUT=…` | Download a completed job's audio |
| `make dev` | Engine in Docker + Vite dev server on the host |
| `make check` | Compose config + Python syntax + frontend build |
| `make test-engine` | Backend API tests in a lightweight container |
| `make test` | All checks and tests |
| `make smoke` | Generate a test WAV through the running API |
| `make backup` | Tar voices/history into `./backups` |
| `make model-reset` | Delete only the cached model weights |
| `make clean` | Delete containers and **all** local data |
| `make help` | Show the full target list |

Acceleration is chosen automatically. Override with `ACCEL=cpu` or
`ACCEL=gpu`:

```bash
make up ACCEL=cpu
make build ACCEL=gpu
```

## API

The engine is available at `http://localhost:8000/api`, with interactive docs
at <http://localhost:8000/api/docs>. The web container proxies the same paths
through `http://localhost:8088/api`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Load status, device, model, voice/output counts |
| `GET` | `/api/info` | Limits, formats, sample rate, preview text |
| `GET` | `/api/languages` | Full OmniVoice language map |
| `POST` | `/api/model/reload` | Retry a failed model load |
| `GET` | `/api/voices` | List voice profiles |
| `POST` | `/api/voices` | Train a profile (multipart) |
| `POST` | `/api/voices/{id}/retrain` | Replace audio/transcript or metadata |
| `PATCH` | `/api/voices/{id}` | Rename a profile |
| `DELETE` | `/api/voices/{id}` | Delete a profile |
| `GET` | `/api/voices/{id}/reference` | Reference WAV |
| `GET/POST` | `/api/voices/{id}/preview` | Fetch/generate a preview |
| `POST` | `/api/tts` | Synthesize speech (JSON) |
| `GET` | `/api/outputs` | Generation history |
| `GET` | `/api/outputs/{id}` | Fetch audio (`?download=1` to attach) |
| `DELETE` | `/api/outputs/{id}` | Delete a generation |
| `GET` | `/api/jobs` | Queue counts and recent jobs |
| `POST` | `/api/jobs/tts` | Enqueue speech synthesis |
| `POST` | `/api/jobs/voices` | Enqueue voice training |
| `POST` | `/api/jobs/voices/{id}/retrain` | Enqueue retraining |
| `POST` | `/api/jobs/voices/{id}/preview` | Enqueue a preview |
| `GET` | `/api/jobs/{id}` | Job status, progress, result, error |
| `POST` | `/api/jobs/{id}/cancel` | Cancel queued/running job |
| `POST` | `/api/jobs/cancel-queued` | Cancel every queued job |
| `DELETE` | `/api/jobs/{id}` | Remove a finished job record |
| `GET` | `/api/jobs/{id}/audio` | Fetch a completed job's audio |
| `POST` | `/api/v1/audio/speech` | OpenAI-compatible speech shim |

### `POST /api/tts`

```bash
curl -X POST http://localhost:8000/api/tts \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Hello from OmniVoice Studio.",
    "mode": "voice",
    "voice_id": "abc123def456",
    "language": "en",
    "speed": 1.0,
    "num_step": 32,
    "response_format": "wav"
  }' --output hello.wav
```

`mode` can be `voice`, `design`, or `auto`. For `design`, pass `instruct`
instead of `voice_id`. The response includes `X-Output-Id`,
`X-Audio-Duration`, `X-Generation-Seconds`, and `X-RTF` headers.

For Portuguese variants, send `language: "pt"` plus
`language_variant: "pt-PT"` (or `pt-BR`) together with a voice profile tagged
with the same variant. This keeps compatibility with the single `pt` model
language while enforcing the reference-accent choice.

### Train with curl

Voice creation and retraining require `consent=true`. Only do this for voices
you own or have explicit permission to use.

```bash
curl -X POST http://localhost:8000/api/voices \
  -F 'name=Alice' \
  -F 'audio=@alice.wav' \
  -F 'transcript=The exact words spoken in the clip.' \
  -F 'language=en' \
  -F 'consent=true'
```

### OpenAI-compatible shim

Point any OpenAI-compatible client at `http://localhost:8000/api/v1` with any
API key. The `voice` field accepts a profile name/id, an OpenAI alias (mapped to
auto voice), or a free-form design description.

```bash
curl -X POST http://localhost:8000/api/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"omnivoice","input":"Hello.","voice":"Alice","response_format":"wav"}' \
  --output hello.wav
```

## Configuration

Copy `.env.example` to `.env` (the Makefile does this automatically). The most
useful variables:

| Variable | Default | Description |
| --- | --- | --- |
| `BIND_ADDR` | `127.0.0.1` | Host bind address; use `0.0.0.0` for LAN access |
| `WEB_PORT` | `8088` | Web UI port |
| `ENGINE_PORT` | `8000` | API port |
| `DEVICE` | `auto` | `auto`, `cpu`, `cuda:0`, `mps`, or `xpu` |
| `OMNIVOICE_MODEL` | `k2-fsa/OmniVoice` | Hugging Face model id |
| `OMNIVOICE_ASR_MODEL` | `openai/whisper-large-v3-turbo` | Whisper used for blank transcripts |
| `OMNIVOICE_ASR_DEVICE` | same as model | Put Whisper on another device, e.g. `cpu` |
| `OMNIVOICE_LOAD_ASR` | `0` | `1` loads Whisper at startup (more VRAM) |
| `HF_ENDPOINT` | `https://huggingface.co` | Mirror endpoint if needed |
| `HF_TOKEN` | unset | Token for gated/private Hugging Face repos |
| `MAX_INPUT_CHARS` | `8000` | Maximum synthesis text length |
| `MAX_UPLOAD_MB` | `50` | Reference upload limit |
| `MAX_VOICE_SECONDS` | `30` | Reference clip length limit |
| `MAX_QUEUE_SIZE` | `50` | Maximum queued jobs before HTTP 429 |
| `MAX_JOB_HISTORY` | `200` | Finished job records kept in memory |
| `CORS_ORIGINS` | local web origins | Comma-separated origins for direct API access |
| `TORCH_INDEX_URL` | auto (CPU or cu128) | Override for a different CUDA build |
| `TORCH_VERSION` | `2.8.0` | PyTorch/torchaudio version |

### GPU notes

The GPU stack uses CUDA 12.8 wheels by default:

```bash
make up-gpu
```

If your driver is older, override the wheel index, for example CUDA 12.6:

```bash
TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126 make up-gpu
```

The container must be able to see the GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

If that fails, install the NVIDIA Container Toolkit and restart Docker.

### CPU notes

CPU inference works but is much slower. Use `num_step: 16` in the UI for faster
generation, and consider a smaller Whisper model:

```dotenv
OMNIVOICE_ASR_MODEL=openai/whisper-small
OMNIVOICE_ASR_DEVICE=cpu
```

Typing the reference transcript avoids loading Whisper entirely.

## Data, backup, and privacy

- All persistent data is in the `omnivoice-studio_omnivoice-data` volume.
- `make backup` writes `voices/` and `outputs/` into `./backups/`.
- Job records are in-memory for the engine session; generated files persist.
- `make model-reset` removes only the Hugging Face cache.
- `make clean` removes the volume, including trained voices and history.
- The only required network access is the initial model/Whisper download from
  Hugging Face. Inference is local.
- Ports bind to `127.0.0.1` by default. Change `BIND_ADDR=0.0.0.0` only if you
  understand the exposure.

## Development

```bash
make dev        # engine container + Vite dev server on http://127.0.0.1:5173
make check      # compose config, Python compile, frontend production build
make test       # check + backend API tests
```

Project layout:

```text
.
├── Makefile
├── docker-compose.yml
├── docker-compose.cpu.yml
├── docker-compose.gpu.yml
├── engine/                 # FastAPI + OmniVoice
│   ├── app/
│   │   ├── main.py         # routes
│   │   ├── runtime.py      # core TTS/training/preview operations
│   │   ├── jobs.py         # FIFO queue, cancellation, progress
│   │   ├── model_manager.py
│   │   ├── storage.py
│   │   ├── audio.py
│   │   └── data/languages.tsv
│   ├── tests/
│   └── Dockerfile
├── web/                    # Vue 3 + Vite + TypeScript
│   ├── src/
│   │   ├── views/          # Studio, Voices, Design, Jobs, History, About
│   │   ├── components/
│   │   └── lib/            # API, job polling, store, formatting
│   ├── nginx.conf
│   └── Dockerfile
└── scripts/tts.py          # dependency-free CLI helper
```

The frontend is a single-page app with six views: Studio, Voices, Design, Jobs,
History, and About. The engine exposes a JSON/multipart API and stores profiles
as directories with a `meta.json`, `reference.wav`, and cached `prompt.pt`.

## Troubleshooting

**The model takes forever to load / container is unhealthy**
The first run downloads several GB. Watch `make logs-engine`. The health
endpoint responds during loading; the UI polls until `model_loaded` is true.
`make wait` prints the final health payload.

**Hugging Face is blocked**
Set a mirror in `.env`:

```dotenv
HF_ENDPOINT=https://hf-mirror.com
```

Then `make restart`.

**Out of memory**
Use a smaller Whisper model or `OMNIVOICE_LOAD_ASR=0` (the default), lower
`num_step` to 16, and use shorter text. For GPU OOM, confirm no other process is
using VRAM.

**Microphone recording does not work**
Browsers require a secure context. `http://localhost` and `http://127.0.0.1`
are treated as secure; a plain-HTTP LAN address may not be. Upload a file
instead.

**Port already in use**
Change `WEB_PORT`/`ENGINE_PORT` in `.env`, then `make start`.

**Permission errors on a bind-mounted data directory**
The entrypoint drops to UID 1000 (`appuser`). If you replace the named volume
with a host bind mount, make it writable by UID 1000 or run the container as
your user.

**Reset everything**
`make clean` deletes containers, voices, history, and the model cache. A fresh
`make up` starts from zero.

## Responsible use

OmniVoice supports voice cloning. Only clone voices you own or have explicit
permission to use. Do not use this project for impersonation, fraud,
harassment, scams, or any other illegal or harmful activity. The app requires a
consent confirmation before training, but that checkbox is not a substitute for
the law or for respect for the person whose voice you are using.

## Credits and license

- [OmniVoice](https://github.com/k2-fsa/OmniVoice) — zero-shot multilingual TTS.
- [Whisper](https://github.com/openai/whisper) via Hugging Face Transformers,
  used only for optional reference transcription.
- Language map derived from OmniVoice's `docs/lang_id_name_map.tsv`.

The application code in this repository is provided under the Apache-2.0
license. OmniVoice model weights have their own license; check the model card at
<https://huggingface.co/k2-fsa/OmniVoice> before commercial use.

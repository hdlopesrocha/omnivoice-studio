SHELL := /bin/bash
.DEFAULT_GOAL := help

# Load local settings when present. Compose also reads this file.
-include .env

# Make sure command-line and .env overrides reach `docker compose`.
export BIND_ADDR WEB_PORT ENGINE_PORT DEVICE
export TORCH_INDEX_URL TORCH_VERSION

ACCEL ?= auto
HAS_NVIDIA := $(shell command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1 && echo yes)

ifeq ($(ACCEL),auto)
  ifeq ($(HAS_NVIDIA),yes)
    ACCEL := gpu
  else
    ACCEL := cpu
  endif
endif

ifeq ($(ACCEL),gpu)
  COMPOSE_FILES := -f docker-compose.yml -f docker-compose.gpu.yml
else
  COMPOSE_FILES := -f docker-compose.yml -f docker-compose.cpu.yml
endif

COMPOSE := docker compose $(COMPOSE_FILES)
BIND_ADDR ?= 127.0.0.1
HOST := $(if $(filter 0.0.0.0,$(BIND_ADDR)),localhost,$(BIND_ADDR))
WEB_PORT ?= 8088
ENGINE_PORT ?= 8000
API := http://$(HOST):$(ENGINE_PORT)/api
WEB_URL := http://$(HOST):$(WEB_PORT)
WAIT_TIMEOUT ?= 3600
JSON := python3 -m json.tool
DATA_VOLUME := omnivoice-studio_omnivoice-data

.PHONY: help env build up start up-gpu up-cpu build-gpu build-cpu down restart \
	logs logs-engine logs-web ps wait status info voices outputs jobs job cancel cancel-queued \
	job-audio voice train say tts preview dev dev-web install build-web check test test-engine \
	smoke open urls backup model-reset clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nOmniVoice Studio\n\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf "\nAcceleration: \033[33m%s\033[0m (override with ACCEL=cpu or ACCEL=gpu)\n\n" "$(ACCEL)"

.env:
	@cp .env.example .env
	@echo "Created .env from .env.example"

env: .env ## Create .env if it does not exist

build: .env ## Build the engine and web images for the detected accelerator
	$(COMPOSE) build

build-gpu: .env ## Build the GPU images
	@$(MAKE) build ACCEL=gpu

build-cpu: .env ## Build the CPU images
	@$(MAKE) build ACCEL=cpu

up: .env ## Build and start everything (auto-detects NVIDIA GPU)
	$(COMPOSE) up -d --build
	@printf "\n  Web app:  %s\n  API docs: %s/docs\n\n" "$(WEB_URL)" "$(API)"
	@echo "First boot downloads the model. Run 'make wait' to follow readiness."

start: .env ## Start already-built containers
	$(COMPOSE) up -d
	@printf "\n  Web app:  %s\n  API docs: %s/docs\n\n" "$(WEB_URL)" "$(API)"

up-gpu: .env ## Force the GPU stack
	@$(MAKE) up ACCEL=gpu

up-cpu: .env ## Force the CPU stack
	@$(MAKE) up ACCEL=cpu

down: ## Stop and remove containers (keeps data)
	$(COMPOSE) down --remove-orphans

restart: .env ## Recreate containers to apply .env changes
	$(COMPOSE) up -d --force-recreate

logs: ## Follow all container logs
	$(COMPOSE) logs -f --tail=200

logs-engine: ## Follow the engine logs
	$(COMPOSE) logs -f --tail=200 engine

logs-web: ## Follow the web logs
	$(COMPOSE) logs -f --tail=200 web

ps: ## Show container status
	$(COMPOSE) ps

wait: ## Wait until the OmniVoice model is loaded
	@echo "Waiting for OmniVoice to become ready (timeout $(WAIT_TIMEOUT)s)..."
	@start=$$(date +%s); \
	while true; do \
		body=$$(curl -fsS "$(API)/health" 2>/dev/null || true); \
		if echo "$$body" | grep -Eq '"model_loaded"[[:space:]]*:[[:space:]]*true'; then \
			echo ""; echo "OmniVoice is ready."; echo "$$body" | $(JSON); break; \
		fi; \
		if echo "$$body" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"error"'; then \
			echo ""; echo "OmniVoice failed to load:"; echo "$$body" | $(JSON); exit 1; \
		fi; \
		now=$$(date +%s); \
		if [ $$((now-start)) -ge $(WAIT_TIMEOUT) ]; then \
			echo ""; echo "Timed out. Check 'make logs-engine'."; exit 1; \
		fi; \
		printf '.'; sleep 5; \
	done

status: ## Print engine health
	@curl -fsS "$(API)/health" | $(JSON)

info: ## Print engine capabilities and limits
	@curl -fsS "$(API)/info" | $(JSON)

voices: ## List trained voice profiles
	@curl -fsS "$(API)/voices" | $(JSON)

outputs: ## List recent generations
	@curl -fsS "$(API)/outputs" | $(JSON)

jobs: ## List queued, running, and recent jobs
	@curl -fsS "$(API)/jobs" | $(JSON)

job: ## Show a job: make job JOB_ID=...
	@test -n "$(JOB_ID)" || (echo "Usage: make job JOB_ID=..."; exit 1)
	@curl -fsS "$(API)/jobs/$(JOB_ID)" | $(JSON)

cancel: ## Cancel a job: make cancel JOB_ID=...
	@test -n "$(JOB_ID)" || (echo "Usage: make cancel JOB_ID=..."; exit 1)
	@curl -fsS -X POST "$(API)/jobs/$(JOB_ID)/cancel" | $(JSON)

cancel-queued: ## Cancel every queued job
	@curl -fsS -X POST "$(API)/jobs/cancel-queued" | $(JSON)

job-audio: ## Download a completed job's audio: make job-audio JOB_ID=... [OUT=file]
	@test -n "$(JOB_ID)" || (echo "Usage: make job-audio JOB_ID=... [OUT=file]"; exit 1)
	@if [ -n "$(OUT)" ]; then \
		curl -fsS "$(API)/jobs/$(JOB_ID)/audio?download=1" -o "$(OUT)"; \
		echo "Wrote $(OUT)"; \
	else \
		curl -fsS -OJ "$(API)/jobs/$(JOB_ID)/audio?download=1"; \
	fi

voice: ## Train a profile: make voice NAME=Alice AUDIO=./alice.wav [TRANSCRIPT="..."] [LANG=en]
	@if [ -z "$(NAME)" ] || [ -z "$(AUDIO)" ]; then \
		echo "Usage: make voice NAME='Alice' AUDIO=./alice.wav [TRANSCRIPT='exact words'] [LANG=en]"; \
		exit 1; \
	fi
	@if [ ! -f "$(AUDIO)" ]; then echo "Audio file not found: $(AUDIO)"; exit 1; fi
	@curl -fsS -X POST "$(API)/voices" \
		--form-string "name=$(NAME)" \
		-F "audio=@$(AUDIO)" \
		--form-string "transcript=$(TRANSCRIPT)" \
		--form-string "language=$(LANG)" \
		--form-string "consent=true" | $(JSON)

train: voice ## Alias for voice

say: ## Synthesize: make say TEXT="Hello" [VOICE_ID=...] [MODE=voice|auto|design] [INSTRUCT="..."] [LANG=en] [OUT=out.wav]
	@if [ -z "$(TEXT)" ]; then \
		echo "Usage: make say TEXT='Hello' [VOICE_ID=...] [MODE=voice|auto|design] [INSTRUCT='...'] [LANG=en] [OUT=out.wav]"; \
		exit 1; \
	fi
	@python3 scripts/tts.py \
		--api "$(API)" \
		--text "$(TEXT)" \
		--mode "$(or $(MODE),$(if $(VOICE_ID),voice,auto))" \
		--voice-id "$(VOICE_ID)" \
		--instruct "$(INSTRUCT)" \
		--language "$(LANG)" \
		--format "$(or $(FORMAT),wav)" \
		--out "$(or $(OUT),out.wav)"

tts: say ## Alias for say

preview: ## Generate a voice preview: make preview VOICE_ID=...
	@test -n "$(VOICE_ID)" || (echo "Usage: make preview VOICE_ID=..."; exit 1)
	@curl -fsS -X POST "$(API)/voices/$(VOICE_ID)/preview" -o "preview-$(VOICE_ID).wav"
	@echo "Wrote preview-$(VOICE_ID).wav"

dev: .env ## Run the engine in Docker and Vite dev server on the host
	$(COMPOSE) up -d --build engine
	@echo "Engine API: $(API)"
	cd web && npm install && VITE_API_PROXY_TARGET=http://$(HOST):$(ENGINE_PORT) npm run dev

dev-web: ## Run only the Vite dev server (engine must already be running)
	cd web && npm install && VITE_API_PROXY_TARGET=http://$(HOST):$(ENGINE_PORT) npm run dev

install: ## Install frontend dependencies
	cd web && npm install

build-web: ## Build the frontend bundle
	cd web && npm run build

check: ## Validate compose files, Python syntax, and the frontend build
	$(COMPOSE) config -q
	python3 -m compileall -q engine/app
	cd web && npm ci && npm run build

test-engine: ## Run backend API tests in a lightweight container
	docker run --rm \
		-v "$(CURDIR)/engine:/app" \
		-w /app \
		python:3.11-slim \
		sh -c "apt-get update -qq && apt-get install -y -qq ffmpeg libsndfile1 >/dev/null && pip install -q -r requirements-test.txt && pytest -q"

test: check test-engine ## Run all checks and backend tests

smoke: wait ## Generate a short test WAV through the API
	@curl -fsS -X POST "$(API)/tts" \
		-H "Content-Type: application/json" \
		-d '{"text":"Hello from OmniVoice Studio. This is a local text to speech test.","mode":"auto","response_format":"wav"}' \
		-o /tmp/omnivoice-smoke.wav
	@echo "Wrote /tmp/omnivoice-smoke.wav"

open: ## Open the web app in a browser
	@(xdg-open "$(WEB_URL)" >/dev/null 2>&1 || open "$(WEB_URL)" >/dev/null 2>&1 || echo "Open $(WEB_URL)")

urls: ## Print the local URLs
	@printf "Web app:  %s\nAPI docs: %s/docs\nHealth:   %s/health\n" "$(WEB_URL)" "$(API)" "$(API)"

backup: ## Back up voices and history into ./backups
	@mkdir -p backups
	docker run --rm \
		-v $(DATA_VOLUME):/data:ro \
		-v "$(CURDIR)/backups:/backup" \
		alpine:3.20 \
		sh -c "tar czf /backup/omnivoice-data-$$(date +%Y%m%d-%H%M%S).tar.gz -C /data voices outputs"
	@ls -lh backups

model-reset: ## Delete cached model weights (keeps voices and history)
	@read -p "Delete cached Hugging Face models? They will download again on next start. [y/N] " ans; \
	if [[ "$$ans" == [yY] ]]; then \
		docker run --rm -v $(DATA_VOLUME):/data alpine:3.20 sh -c "rm -rf /data/hf"; \
		echo "Model cache removed."; \
	else \
		echo "Cancelled."; \
	fi

clean: ## Stop containers and delete ALL local data (voices, history, model cache)
	@read -p "This deletes all trained voices, generated audio, and cached models. Continue? [y/N] " ans; \
	if [[ "$$ans" == [yY] ]]; then \
		$(COMPOSE) down -v --remove-orphans; \
		echo "Data volume removed."; \
	else \
		echo "Cancelled."; \
	fi

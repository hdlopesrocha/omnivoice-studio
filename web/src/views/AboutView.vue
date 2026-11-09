<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Database,
  ExternalLink,
  HardDrive,
  Info,
  Languages,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
} from '@lucide/vue'
import CodeBlock from '../components/CodeBlock.vue'
import { api, getErrorMessage } from '../lib/api'
import { formatDate } from '../lib/format'
import { modelReady, refreshHealth, store } from '../lib/store'
import { toast } from '../lib/toast'
import type { Info as EngineInfo } from '../lib/types'

const info = ref<EngineInfo | null>(null)
const loading = ref(false)

const health = computed(() => store.health)

const statusLabel = computed(() => {
  if (!store.online) return 'Engine unreachable'
  if (!health.value) return 'Connecting'
  if (health.value.status === 'ok') return 'Ready'
  if (health.value.status === 'error') return 'Failed to load'
  return 'Warming up'
})

const uptimeLabel = computed(() => {
  const seconds = health.value?.uptime_seconds || 0
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
})

const quickstart = `# Start the whole stack (auto-detects an NVIDIA GPU)
make up

# Follow model warm-up
make wait

# Open the studio
open http://localhost:8088`

const trainCommand = `# Train a reusable voice profile from a reference clip
make voice NAME=Alice AUDIO=./alice.wav \\
  TRANSCRIPT="The exact words spoken in the clip." LANG=en`

const sayCommand = `# Synthesize from the command line
make say TEXT="Hello from my local OmniVoice." \\
  VOICE_ID=<voice-id> OUT=hello.wav`

async function loadInfo(): Promise<void> {
  loading.value = true
  try {
    await refreshHealth()
    info.value = await api.info()
  } catch (error) {
    toast('error', 'Could not load engine info', getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function retry(): Promise<void> {
  try {
    await api.reloadModel()
    toast('info', 'Reloading model', 'The engine is restarting the OmniVoice loader.')
    await refreshHealth()
    info.value = await api.info()
  } catch (error) {
    toast('error', 'Could not reload the model', getErrorMessage(error))
  }
}

onMounted(loadInfo)
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Local by design.</h1>
        <p class="page-subtitle">
          OmniVoice Studio runs entirely on your machine. The Vue app, the
          FastAPI engine, the model weights, your trained voices, and every
          generated file live in Docker and a local data volume.
        </p>
      </div>
      <a class="btn btn-secondary" :href="api.docsUrl()" target="_blank" rel="noreferrer">
        <ExternalLink :size="14" />
        API docs
      </a>
    </div>

    <div class="about-grid">
      <div class="stack">
        <section class="card card-pad">
          <div class="card-head">
            <div>
              <div class="card-title">Runtime</div>
              <div class="card-sub">Live state reported by the engine.</div>
            </div>
            <span
              class="status-pill"
              :class="
                modelReady
                  ? 'ok'
                  : !store.online || health?.status === 'error'
                    ? 'error'
                    : 'loading'
              "
            >
              <span class="status-dot" />
              {{ statusLabel }}
            </span>
          </div>

          <div class="info-grid">
            <div class="info-tile">
              <div class="info-tile-label">Model</div>
              <div class="info-tile-value">{{ health?.model_id || info?.model_id || '—' }}</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Device</div>
              <div class="info-tile-value">
                <Cpu :size="12" style="vertical-align: -1px; margin-right: 4px" />
                {{ health?.device || info?.device || '—' }}
              </div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">ASR</div>
              <div class="info-tile-value">{{ health?.asr_model || '—' }}</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Sample rate</div>
              <div class="info-tile-value">
                {{ ((health?.sample_rate || info?.sample_rate || 0) / 1000).toFixed(0) }} kHz
              </div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Trained voices</div>
              <div class="info-tile-value">{{ health?.voices ?? 0 }}</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Generations</div>
              <div class="info-tile-value">{{ health?.outputs ?? 0 }}</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Active jobs</div>
              <div class="info-tile-value">{{ health?.jobs ?? 0 }}</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Queue limit</div>
              <div class="info-tile-value">{{ info?.max_queue_size ?? 50 }}</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Uptime</div>
              <div class="info-tile-value">{{ uptimeLabel }}</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Version</div>
              <div class="info-tile-value">{{ health?.version || info?.version || '1.0.0' }}</div>
            </div>
          </div>

          <div
            v-if="health?.status === 'error'"
            class="banner error"
            style="margin: 16px 0 0"
          >
            <div class="banner-icon"><AlertTriangle :size="17" /></div>
            <div class="banner-body">
              <div class="banner-title">Model load error</div>
              <div class="banner-text">{{ health.error }}</div>
            </div>
            <div class="banner-actions">
              <button type="button" class="btn btn-secondary btn-sm" @click="retry">
                <RefreshCw :size="13" />
                Retry
              </button>
            </div>
          </div>

          <div v-else class="row" style="margin-top: 16px; flex-wrap: wrap">
            <span class="badge mint">
              <CheckCircle2 :size="11" />
              Local processing
            </span>
            <span class="badge">
              <HardDrive :size="11" />
              Docker volume
            </span>
            <span class="badge">
              <Languages :size="11" />
              {{ info?.languages || 600 }}+ languages
            </span>
            <span v-if="health?.asr_loaded" class="badge violet">
              <Sparkles :size="11" />
              Whisper loaded
            </span>
          </div>
        </section>

        <section class="card card-pad">
          <div class="card-head">
            <div>
              <div class="card-title">How it works</div>
              <div class="card-sub">Three moving parts, one local stack.</div>
            </div>
            <Server :size="17" class="muted" />
          </div>
          <div class="steps">
            <div class="step">
              <div class="step-badge">1</div>
              <div>
                <div class="step-title">Reference clip → voice profile</div>
                <div class="step-text">
                  The engine decodes your clip to 24 kHz mono, optionally
                  auto-transcribes it with Whisper, and caches an OmniVoice
                  voice-clone prompt in <span class="mono">/data/voices</span>.
                </div>
              </div>
            </div>
            <div class="step">
              <div class="step-badge">2</div>
              <div>
                <div class="step-title">Text → speech</div>
                <div class="step-text">
                  The FastAPI engine loads the cached prompt, runs OmniVoice
                  with your language, speed, and quality settings, and returns
                  WAV, MP3, or FLAC.
                </div>
              </div>
            </div>
            <div class="step">
              <div class="step-badge">3</div>
              <div>
                <div class="step-title">Everything stays local</div>
                <div class="step-text">
                  The Vue app talks to the engine through nginx inside the
                  Compose network. Generated audio and metadata are written to
                  <span class="mono">/data/outputs</span>.
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="card card-pad">
          <div class="card-head">
            <div>
              <div class="card-title">Command line</div>
              <div class="card-sub">The Makefile orchestrates the same API.</div>
            </div>
            <Database :size="17" class="muted" />
          </div>
          <div class="stack-sm">
            <CodeBlock :code="quickstart" label="Quick start" />
            <CodeBlock :code="trainCommand" label="Train a voice" />
            <CodeBlock :code="sayCommand" label="Synthesize" />
          </div>
        </section>
      </div>

      <div class="stack">
        <section class="card card-pad">
          <div class="card-head" style="margin-bottom: 10px">
            <div>
              <div class="card-title">Training, precisely</div>
              <div class="card-sub">Zero-shot enrollment, not weight fine-tuning.</div>
            </div>
            <Info :size="16" class="muted" />
          </div>
          <p class="muted" style="font-size: 12.5px; line-height: 1.6">
            OmniVoice is a zero-shot model. “Training” a voice in this app means
            encoding a reference clip into a reusable prompt — the model weights
            are never changed. This is what makes a 3–10 second sample enough,
            and why the result is instant compared with fine-tuning.
          </p>
          <p class="muted" style="font-size: 12.5px; line-height: 1.6; margin-top: 10px">
            If you need to adapt the model itself, OmniVoice publishes LoRA
            fine-tuning recipes upstream. That is a separate, GPU-heavy workflow
            and is intentionally not part of this local studio.
          </p>
        </section>

        <section class="card card-pad">
          <div class="card-head" style="margin-bottom: 10px">
            <div>
              <div class="card-title">Privacy</div>
              <div class="card-sub">No telemetry, no hosted API.</div>
            </div>
            <ShieldCheck :size="16" class="text-success" />
          </div>
          <ul class="tips-list" style="padding-left: 16px">
            <li>Model weights download from Hugging Face on first boot.</li>
            <li>After that, inference and voice encoding are fully offline.</li>
            <li>Voices, history, and cached models live in the Docker volume.</li>
            <li>Ports bind to 127.0.0.1 by default.</li>
            <li>Run <span class="mono">make clean</span> to delete everything.</li>
          </ul>
        </section>

        <section class="ethics">
          <div class="ethics-title">
            <AlertTriangle :size="15" />
            Use voices responsibly
          </div>
          <div class="ethics-text">
            Only clone voices you own or have explicit permission to use. Do not
            use this project for impersonation, fraud, harassment, or any other
            illegal or harmful activity. The app requires a consent confirmation
            before training, but that checkbox is not a substitute for the law or
            for respect for the person whose voice you are using.
          </div>
        </section>

        <section class="card card-pad">
          <div class="card-head" style="margin-bottom: 8px">
            <div>
              <div class="card-title">Stack</div>
              <div class="card-sub">Built with local-first defaults.</div>
            </div>
          </div>
          <div class="info-grid">
            <div class="info-tile">
              <div class="info-tile-label">Frontend</div>
              <div class="info-tile-value">Vue 3 + Vite + TypeScript</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Engine</div>
              <div class="info-tile-value">FastAPI + OmniVoice</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Serving</div>
              <div class="info-tile-value">nginx + Docker Compose</div>
            </div>
            <div class="info-tile">
              <div class="info-tile-label">Orchestration</div>
              <div class="info-tile-value">Makefile</div>
            </div>
          </div>
          <div class="divider" />
          <div class="row-between">
            <span class="muted-2" style="font-size: 11px">
              Started {{ formatDate(health ? new Date(Date.now() - (health.uptime_seconds || 0) * 1000).toISOString() : null) }}
            </span>
            <button type="button" class="btn btn-ghost btn-sm" :disabled="loading" @click="loadInfo">
              <RefreshCw :size="12" />
              {{ loading ? 'Refreshing…' : 'Refresh' }}
            </button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

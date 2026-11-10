<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Ban,
  Clock3,
  Download,
  Layers3,
  ListPlus,
  Sparkles,
  UserRound,
  Wand2,
} from '@lucide/vue'
import AudioButton from '../components/AudioButton.vue'
import GenerationSettings from '../components/GenerationSettings.vue'
import { api, getErrorMessage } from '../lib/api'
import { formatTime } from '../lib/format'
import {
  advancedToRequest,
  defaultAdvanced,
} from '../lib/generation'
import {
  isJobActive,
  jobStatusClass,
  jobStatusLabel,
  waitForJob,
} from '../lib/jobs'
import { languageVariant, modelLanguage } from '../lib/language'
import {
  modelReady,
  refreshHistory,
  store,
  upsertJob,
} from '../lib/store'
import { toast } from '../lib/toast'
import type { AudioFormat, Job, TTSMode } from '../lib/types'

const batchText = ref('')
const splitMode = ref<'blank' | 'line'>('blank')
const mode = ref<'voice' | 'auto' | 'design'>('voice')
const voiceId = ref<string | null>(null)
const instruct = ref('')
const language = ref<string | null>(null)
const speed = ref(1)
const numStep = ref(32)
const format = ref<AudioFormat>('wav')
const advanced = reactive(defaultAdvanced())
const activeJob = ref<Job | null>(null)
const resultJob = ref<Job | null>(null)
const error = ref('')

let jobToken = 0
let alive = true

const items = computed(() => {
  const raw = batchText.value
  if (!raw.trim()) return []
  const parts =
    splitMode.value === 'blank'
      ? raw.split(/\n\s*\n/)
      : raw.split(/\n/)
  return parts.map((item) => item.trim()).filter(Boolean)
})

const itemError = computed(() => {
  if (items.value.length > 50) return 'Batch is limited to 50 items.'
  if (items.value.some((item) => item.length > 8000)) {
    return 'Each batch item must be 8,000 characters or less.'
  }
  return ''
})

const selectedVoice = computed(
  () => store.voices.find((voice) => voice.id === voiceId.value) || null,
)
const selectedLanguage = computed(
  () => store.languages.find((item) => item.id === language.value) || null,
)
const variantIssue = computed(() => {
  const variant = selectedLanguage.value
  if (!variant?.requires_voice) return ''
  if (mode.value !== 'voice') {
    return `${variant.name} needs a trained voice profile. Auto voice and voice design cannot guarantee the accent.`
  }
  if (selectedVoice.value?.language !== variant.id) {
    return `Select a voice tagged ${variant.name}, or retrain/tag your voice with a matching reference clip.`
  }
  return ''
})
const designIssue = computed(() =>
  mode.value === 'design' && !instruct.value.trim()
    ? 'Describe the designed voice first.'
    : '',
)
const activeJobRunning = computed(() => isJobActive(activeJob.value))
const canGenerate = computed(
  () =>
    modelReady.value &&
    !activeJobRunning.value &&
    !itemError.value &&
    !variantIssue.value &&
    !designIssue.value &&
    items.value.length > 0 &&
    (mode.value !== 'voice' || Boolean(voiceId.value)),
)
const resultItems = computed(() => resultJob.value?.result?.items || [])
const zipUrl = computed(() =>
  resultJob.value ? api.jobZipUrl(resultJob.value.id) : '',
)

watch(
  () => store.voices,
  (voices) => {
    if (!voices.length) {
      mode.value = 'auto'
      voiceId.value = null
      return
    }
    if (!voiceId.value || !voices.some((voice) => voice.id === voiceId.value)) {
      voiceId.value = voices[0]?.id || null
      if (mode.value === 'auto') mode.value = 'voice'
    }
  },
  { immediate: true },
)

function useSample(): void {
  batchText.value = [
    'Welcome to OmniVoice Studio. This is the first batch item.',
    'This is the second item. Each paragraph becomes its own audio file.',
    'The third item becomes its own audio file in the batch.',
  ].join('\n\n')
}

async function generate(): Promise<void> {
  if (!modelReady.value) {
    toast('info', 'Model is still warming up', 'Try again when the status pill turns green.')
    return
  }
  if (!canGenerate.value) return

  error.value = ''
  const token = ++jobToken
  try {
    const job = await api.submitBatchJob({
      texts: items.value,
      mode: mode.value as TTSMode,
      voice_id: mode.value === 'voice' ? voiceId.value : null,
      instruct: mode.value === 'design' ? instruct.value.trim() : null,
      language: modelLanguage(language.value),
      language_variant: languageVariant(language.value),
      speed: speed.value,
      num_step: numStep.value,
      response_format: format.value,
      ...advancedToRequest(advanced),
    })
    if (token !== jobToken) return
    activeJob.value = job
    resultJob.value = null
    upsertJob(job)

    const finished = await waitForJob(
      job.id,
      (next) => {
        if (token === jobToken) activeJob.value = next
      },
      () => token !== jobToken || !alive,
    )
    if (token !== jobToken || !alive) return

    if (finished.status === 'completed') {
      activeJob.value = null
      resultJob.value = finished
      await refreshHistory()
      toast(
        'success',
        'Batch complete',
        `${finished.result?.count || items.value.length} audio file(s) generated.`,
      )
    } else if (finished.status === 'cancelled') {
      activeJob.value = null
      error.value = 'Batch cancelled.'
      toast('info', 'Batch cancelled', 'The job was removed or stopped.')
    } else {
      activeJob.value = null
      error.value = finished.error || 'Batch failed.'
      toast('error', 'Batch failed', error.value)
    }
  } catch (err) {
    if (token === jobToken) {
      activeJob.value = null
      error.value = getErrorMessage(err)
      toast('error', 'Could not queue batch', error.value)
    }
  }
}

async function cancelActiveJob(): Promise<void> {
  if (!activeJob.value) return
  try {
    const job = await api.cancelJob(activeJob.value.id)
    activeJob.value = job
    upsertJob(job)
    toast(
      'info',
      job.status === 'cancelled' ? 'Batch cancelled' : 'Cancellation requested',
      job.status === 'cancelled'
        ? 'The queued job was removed.'
        : 'The worker will stop after the current item.',
    )
  } catch (err) {
    toast('error', 'Could not cancel batch', getErrorMessage(err))
  }
}

onBeforeUnmount(() => {
  alive = false
  jobToken += 1
})
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Batch synthesis.</h1>
        <p class="page-subtitle">
          Turn a list of paragraphs or lines into separate audio files. One
          queued job, sequential generation, cancellable between items.
        </p>
      </div>
      <span class="badge violet">
        <Layers3 :size="12" />
        Up to 50 items
      </span>
    </div>

    <div class="grid-2">
      <section class="card composer">
        <div class="card-head">
          <div>
            <div class="card-title">Batch script</div>
            <div class="card-sub">
              {{ items.length }} item(s) · {{ batchText.length }} characters
            </div>
          </div>
          <button type="button" class="btn btn-ghost btn-sm" @click="useSample">
            <Sparkles :size="13" />
            Sample
          </button>
        </div>

        <div class="segmented" style="margin-bottom: 12px">
          <button
            type="button"
            class="segment"
            :class="{ active: splitMode === 'blank' }"
            @click="splitMode = 'blank'"
          >
            Split by blank line
          </button>
          <button
            type="button"
            class="segment"
            :class="{ active: splitMode === 'line' }"
            @click="splitMode = 'line'"
          >
            One item per line
          </button>
        </div>

        <textarea
          v-model="batchText"
          class="textarea composer-textarea no-resize"
          placeholder="Paste multiple paragraphs or lines here…"
        />

        <div class="composer-foot">
          <span class="composer-count">
            {{ items.length }} / 50 items
          </span>
          <button
            type="button"
            class="btn btn-primary btn-lg"
            :disabled="!canGenerate"
            @click="generate"
          >
            <ListPlus :size="16" />
            Generate batch
          </button>
        </div>

        <p v-if="itemError" class="field-error" style="margin-top: 10px">
          {{ itemError }}
        </p>
        <p v-if="variantIssue" class="field-error" style="margin-top: 10px">
          {{ variantIssue }}
        </p>
        <p v-if="designIssue" class="field-error" style="margin-top: 10px">
          {{ designIssue }}
        </p>
        <p v-if="error" class="field-error" style="margin-top: 10px">
          {{ error }}
        </p>
      </section>

      <div class="stack">
        <section class="card card-pad">
          <div class="card-head">
            <div>
              <div class="card-title">Voice</div>
              <div class="card-sub">Use one voice for the whole batch.</div>
            </div>
            <UserRound :size="17" class="muted" />
          </div>

          <div class="tabs" style="margin-bottom: 14px">
            <button
              type="button"
              class="tab"
              :class="{ active: mode === 'voice' }"
              :disabled="!store.voices.length"
              @click="mode = 'voice'"
            >
              My voice
            </button>
            <button
              type="button"
              class="tab"
              :class="{ active: mode === 'auto' }"
              @click="mode = 'auto'"
            >
              Auto
            </button>
            <button
              type="button"
              class="tab"
              :class="{ active: mode === 'design' }"
              @click="mode = 'design'"
            >
              Design
            </button>
          </div>

          <template v-if="mode === 'voice'">
            <select v-if="store.voices.length" v-model="voiceId" class="select">
              <option
                v-for="voice in store.voices"
                :key="voice.id"
                :value="voice.id"
              >
                {{ voice.name }}
              </option>
            </select>
            <div v-else class="empty-state" style="min-height: 120px">
              <div class="empty-title">No trained voices yet</div>
              <RouterLink to="/voices" class="btn btn-primary btn-sm" style="margin-top: 10px">
                Train a voice
              </RouterLink>
            </div>
            <div v-if="selectedVoice" class="voice-select-card" style="margin-top: 10px">
              <div class="voice-select-main">
                <div class="voice-select-name">{{ selectedVoice.name }}</div>
                <div class="voice-select-meta">
                  {{ selectedVoice.duration_seconds.toFixed(1) }}s reference ·
                  {{ selectedVoice.language || 'auto language' }}
                </div>
              </div>
              <AudioButton
                :src="api.referenceUrl(selectedVoice.id)"
                label="Reference"
              />
            </div>
          </template>

          <template v-else-if="mode === 'design'">
            <input
              v-model="instruct"
              class="input"
              maxlength="300"
              placeholder="female, low pitch, british accent"
            />
            <span class="field-hint" style="margin-top: 6px">
              Voice design is most stable in English and Chinese.
            </span>
          </template>

          <div v-else class="voice-select-card">
            <div class="voice-avatar" style="background: linear-gradient(135deg, #8b5cf6, #4f46e5)">
              <Wand2 :size="18" />
            </div>
            <div class="voice-select-main">
              <div class="voice-select-name">Auto voice</div>
              <div class="voice-select-meta">
                OmniVoice chooses a voice per item.
              </div>
            </div>
          </div>
        </section>

        <section class="card card-pad">
          <div class="card-head">
            <div>
              <div class="card-title">Generation settings</div>
              <div class="card-sub">Applied to every batch item.</div>
            </div>
          </div>
          <GenerationSettings
            v-model:language="language"
            v-model:speed="speed"
            v-model:num-step="numStep"
            v-model:format="format"
            :languages="store.languages"
            :advanced="advanced"
            :show-style="mode === 'voice'"
          />
        </section>
      </div>
    </div>

    <div class="result-shell">
      <div v-if="activeJob && activeJobRunning" class="card result-card">
        <div class="result-head">
          <div>
            <div class="result-title">
              <span v-if="activeJob.status === 'queued'">
                <Clock3 :size="15" class="muted" />
              </span>
              <span v-else-if="activeJob.status === 'cancelling'">
                <Ban :size="15" class="text-danger" />
              </span>
              <span v-else class="spinner accent" />
              {{
                activeJob.status === 'queued'
                  ? 'Queued'
                  : activeJob.status === 'cancelling'
                    ? 'Cancelling'
                    : 'Generating batch'
              }}
            </div>
            <div class="card-sub">{{ activeJob.message }}</div>
          </div>
          <span class="job-status" :class="jobStatusClass(activeJob)">
            {{ jobStatusLabel(activeJob) }}
          </span>
        </div>

        <div class="progress-track">
          <div
            class="progress-fill"
            :class="{ queued: activeJob.status === 'queued' }"
            :style="{
              width:
                activeJob.status === 'queued'
                  ? '16%'
                  : `${Math.max(4, Math.round(activeJob.progress * 100))}%`,
            }"
          />
        </div>

        <div class="job-meta">
          <span v-if="activeJob.queue_position">
            Position #{{ activeJob.queue_position }}
          </span>
          <span v-if="activeJob.started_at">
            {{ activeJob.elapsed_seconds.toFixed(0) }}s elapsed
          </span>
          <span>{{ activeJob.summary.count || items.length }} item(s)</span>
        </div>

        <div class="job-actions">
          <button
            v-if="activeJob.can_cancel"
            type="button"
            class="btn btn-danger btn-sm"
            @click="cancelActiveJob"
          >
            <Ban :size="13" />
            Cancel batch
          </button>
          <span
            v-else-if="activeJob.status === 'cancelling'"
            class="muted"
            style="font-size: 12px"
          >
            Waiting for the current item to finish…
          </span>
          <RouterLink to="/jobs" class="btn btn-ghost btn-sm">
            View queue
          </RouterLink>
        </div>
      </div>

      <section v-else-if="resultItems.length" class="card card-pad">
        <div class="card-head">
          <div>
            <div class="card-title">Batch results</div>
            <div class="card-sub">{{ resultItems.length }} audio file(s).</div>
          </div>
          <a :href="zipUrl" class="btn btn-secondary btn-sm" download>
            <Download :size="13" />
            Download ZIP
          </a>
        </div>

        <div class="job-list">
          <div
            v-for="(item, index) in resultItems"
            :key="item.id"
            class="job-card finished"
          >
            <div class="job-head">
              <div class="job-icon">{{ index + 1 }}</div>
              <div class="job-main">
                <div class="job-title">{{ item.text_preview }}</div>
                <div class="job-sub">
                  {{ formatTime(item.duration_seconds) }} ·
                  {{ item.voice_name || item.mode }} ·
                  {{ item.format.toUpperCase() }}
                </div>
              </div>
              <AudioButton :src="api.outputUrl(item.id)" label="Play" />
              <a
                :href="api.outputUrl(item.id, true)"
                class="icon-btn"
                title="Download"
                download
              >
                <Download :size="15" />
              </a>
            </div>
          </div>
        </div>
      </section>

      <div v-else class="card result-card">
        <div class="empty-state" style="min-height: 210px">
          <div class="empty-visual">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
          <div class="empty-title">Batch output will appear here</div>
          <div class="empty-text">
            Paste multiple items, choose a voice, and generate. Each item becomes
            a separate file in History.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import {
  Ban,
  Clock3,
  Eraser,
  Info,
  ListPlus,
  Sparkles,
  Wand2,
} from '@lucide/vue'
import GenerationSettings from '../components/GenerationSettings.vue'
import ResultCard from '../components/ResultCard.vue'
import TextAssist from '../components/TextAssist.vue'
import VoiceDesigner from '../components/VoiceDesigner.vue'
import { api, getErrorMessage } from '../lib/api'
import { formatTime, languageName } from '../lib/format'
import {
  isJobActive,
  jobStatusClass,
  jobStatusLabel,
  waitForJob,
} from '../lib/jobs'
import { languageVariant, modelLanguage } from '../lib/language'
import {
  advancedToRequest,
  defaultAdvanced,
} from '../lib/generation'
import {
  modelReady,
  refreshHistory,
  store,
  upsertJob,
} from '../lib/store'
import { toast } from '../lib/toast'
import type { AudioFormat, Job } from '../lib/types'

const text = ref('')
const textArea = ref<HTMLTextAreaElement | null>(null)
const instruct = ref('')
const language = ref<string | null>(null)
const speed = ref(1)
const numStep = ref(32)
const format = ref<AudioFormat>('wav')
const advanced = reactive(defaultAdvanced())
const error = ref('')
const activeJob = ref<Job | null>(null)

const result = ref<{
  url: string
  outputId: string
  duration: number
  rtf: number | null
  format: AudioFormat
  languageLabel: string
} | null>(null)

let jobToken = 0
let alive = true

const presets = [
  { label: 'British narrator', value: 'female, low pitch, british accent' },
  { label: 'Warm male', value: 'male, low pitch, american accent' },
  { label: 'Whisper', value: 'female, whisper' },
  { label: 'Elderly', value: 'elderly, female, slow' },
  { label: 'Child', value: 'child, high pitch' },
  { label: 'Australian', value: 'male, australian accent' },
]

const selectedLanguage = computed(
  () => store.languages.find((item) => item.id === language.value) || null,
)
const languageVariantIssue = computed(() => {
  const variant = selectedLanguage.value
  if (!variant?.requires_voice) return ''
  return `${variant.name} cannot be guaranteed by voice design. Use a trained voice profile in Studio instead.`
})

const activeJobRunning = computed(() => isJobActive(activeJob.value))
const canGenerate = computed(
  () =>
    modelReady.value &&
    !languageVariantIssue.value &&
    text.value.trim().length > 0 &&
    instruct.value.trim().length > 0,
)

function usePreset(value: string): void {
  instruct.value = value
}

function insertToken(token: string): void {
  const element = textArea.value
  if (!element) {
    text.value = `${text.value}${text.value ? ' ' : ''}${token}`
    return
  }
  const start = element.selectionStart ?? text.value.length
  const end = element.selectionEnd ?? start
  text.value = text.value.slice(0, start) + token + text.value.slice(end)
  void nextTick(() => {
    element.focus()
    const position = start + token.length
    element.setSelectionRange(position, position)
  })
}

async function generate(): Promise<void> {
  if (!modelReady.value) {
    toast('info', 'Model is still warming up', 'Try again when the status pill turns green.')
    return
  }
  if (!text.value.trim()) {
    error.value = 'Write some text to synthesize.'
    return
  }
  if (!instruct.value.trim()) {
    error.value = 'Describe the voice you want, or pick a preset.'
    return
  }

  error.value = ''
  const token = ++jobToken

  try {
    const job = await api.submitTtsJob({
      text: text.value.trim(),
      mode: 'design',
      instruct: instruct.value.trim(),
      language: modelLanguage(language.value),
      language_variant: languageVariant(language.value),
      speed: speed.value,
      num_step: numStep.value,
      response_format: format.value,
      ...advancedToRequest(advanced),
    })
    if (token !== jobToken) return
    activeJob.value = job
    upsertJob(job)

    const finished = await waitForJob(
      job.id,
      (next) => {
        if (token === jobToken) activeJob.value = next
      },
      () => token !== jobToken || !alive,
    )
    if (token !== jobToken || !alive) return

    if (finished.status === 'completed' && finished.result?.output_id) {
      const outputId = finished.result.output_id
      const duration = finished.result.duration_seconds || 0
      result.value = {
        url: api.outputUrl(outputId),
        outputId,
        duration,
        rtf: finished.result.rtf ?? null,
        format: finished.result.format || format.value,
        languageLabel: language.value
          ? languageName(language.value, store.languages)
          : 'Auto-detect',
      }
      activeJob.value = null
      await refreshHistory()
      toast(
        'success',
        'Voice designed',
        `${formatTime(duration)} of audio saved to History.`,
      )
    } else if (finished.status === 'cancelled') {
      activeJob.value = null
      error.value = 'Generation cancelled.'
      toast('info', 'Job cancelled', 'The queued job was removed or stopped.')
    } else {
      activeJob.value = null
      error.value = finished.error || 'Generation failed.'
      toast('error', 'Generation failed', error.value)
    }
  } catch (err) {
    if (token === jobToken) {
      activeJob.value = null
      error.value = getErrorMessage(err)
      toast('error', 'Could not queue generation', error.value)
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
      job.status === 'cancelled' ? 'Job cancelled' : 'Cancellation requested',
      job.status === 'cancelled'
        ? 'The queued job was removed.'
        : 'The worker will stop after the current segment.',
    )
  } catch (err) {
    toast('error', 'Could not cancel job', getErrorMessage(err))
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
        <h1 class="page-title">Describe a voice.</h1>
        <p class="page-subtitle">
          No reference audio required. Combine gender, age, pitch, accent, and
          style attributes to design a voice from scratch.
        </p>
      </div>
      <span class="badge violet">
        <Wand2 :size="12" />
        Voice design
      </span>
    </div>

    <div class="grid-2">
      <section class="card composer">
        <div class="card-head">
          <div>
            <div class="card-title">Script</div>
            <div class="card-sub">What should the designed voice say?</div>
          </div>
          <button
            v-if="text"
            type="button"
            class="btn btn-ghost btn-sm"
            @click="text = ''"
          >
            <Eraser :size="13" />
            Clear
          </button>
        </div>

        <textarea
          ref="textArea"
          v-model="text"
          class="textarea composer-textarea no-resize"
          maxlength="8000"
          placeholder="Type or paste the words you want to hear…"
          @keydown.ctrl.enter.prevent="generate"
          @keydown.meta.enter.prevent="generate"
        />

        <TextAssist @insert="insertToken" />

        <div class="field" style="margin-top: 16px">
          <label class="field-label">Voice description</label>
          <input
            v-model="instruct"
            class="input"
            maxlength="300"
            placeholder="female, low pitch, british accent"
          />
          <span class="field-hint">
            Attributes are comma-separated and can be freely combined.
          </span>
        </div>

        <VoiceDesigner @apply="instruct = $event" />

        <div class="sample-prompts">
          <button
            v-for="preset in presets"
            :key="preset.label"
            type="button"
            class="chip"
            :class="{ active: instruct === preset.value }"
            @click="usePreset(preset.value)"
          >
            <Sparkles :size="11" />
            {{ preset.label }}
          </button>
        </div>

        <div class="composer-foot">
          <span class="composer-count">{{ text.length }} / 8000</span>
          <button
            type="button"
            class="btn btn-primary btn-lg"
            :disabled="!canGenerate"
            @click="generate"
          >
            <ListPlus v-if="activeJobRunning" :size="16" />
            <Wand2 v-else :size="16" />
            {{ activeJobRunning ? 'Queue another' : 'Generate speech' }}
          </button>
        </div>

        <p v-if="languageVariantIssue" class="field-error" style="margin-top: 10px">
          {{ languageVariantIssue }}
        </p>
        <p v-if="error" class="field-error" style="margin-top: 10px">
          {{ error }}
        </p>
      </section>

      <div class="stack">
        <section class="card card-pad">
          <div class="card-head">
            <div>
              <div class="card-title">Generation settings</div>
              <div class="card-sub">Language, pacing, quality, and output.</div>
            </div>
            <Wand2 :size="17" class="muted" />
          </div>
          <GenerationSettings
            v-model:language="language"
            v-model:speed="speed"
            v-model:num-step="numStep"
            v-model:format="format"
            :languages="store.languages"
            :advanced="advanced"
          />
        </section>

        <section class="card card-pad">
          <div class="card-head" style="margin-bottom: 10px">
            <div>
              <div class="card-title">A note on voice design</div>
              <div class="card-sub">Cloning is the most stable OmniVoice mode.</div>
            </div>
            <Info :size="16" class="muted" />
          </div>
          <div class="tips-card">
            <div class="tips-title">
              <Info :size="14" />
              Best results
            </div>
            <ul class="tips-list">
              <li>Voice design is strongest in English and Chinese.</li>
              <li>Use short, concrete attributes: gender, pitch, age, accent.</li>
              <li>For a specific real person, train a voice profile instead.</li>
            </ul>
          </div>
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
                    : 'Designing speech'
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
          <span>{{ activeJob.summary.text_preview || 'Voice design' }}</span>
        </div>

        <div class="job-actions">
          <button
            v-if="activeJob.can_cancel"
            type="button"
            class="btn btn-danger btn-sm"
            @click="cancelActiveJob"
          >
            <Ban :size="13" />
            Cancel job
          </button>
          <span
            v-else-if="activeJob.status === 'cancelling'"
            class="muted"
            style="font-size: 12px"
          >
            Waiting for the current segment to finish…
          </span>
          <RouterLink to="/jobs" class="btn btn-ghost btn-sm">
            View queue
          </RouterLink>
        </div>
      </div>

      <ResultCard
        v-else-if="result"
        :src="result.url"
        :output-id="result.outputId"
        :duration="result.duration"
        :rtf="result.rtf"
        :format="result.format"
        voice-label="Designed voice"
        :language-label="result.languageLabel"
        title="Your designed voice"
        subtitle="Saved to History and ready to download."
      />

      <div v-else class="card result-card">
        <div class="empty-state" style="min-height: 210px">
          <div class="empty-visual">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
          <div class="empty-title">Design a voice and hear it here</div>
          <div class="empty-text">
            Describe the voice in words, write a script, and generate. No
            reference recording is needed for this mode.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  ArrowRight,
  AudioLines,
  Ban,
  Clock3,
  Eraser,
  ListPlus,
  Mic2,
  Plus,
  Sparkles,
  UserRound,
  Wand2,
} from '@lucide/vue'
import AudioButton from '../components/AudioButton.vue'
import GenerationSettings from '../components/GenerationSettings.vue'
import TextAssist from '../components/TextAssist.vue'
import ResultCard from '../components/ResultCard.vue'
import { api, getErrorMessage } from '../lib/api'
import {
  formatDate,
  formatTime,
  initials,
  languageName,
  truncate,
  voiceGradient,
} from '../lib/format'
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
import type { AudioFormat, Job, TTSMode } from '../lib/types'

const route = useRoute()
const requestedVoiceId = ref<string | null>(
  typeof route.query.voice === 'string' ? route.query.voice : null,
)

const text = ref('')
const textArea = ref<HTMLTextAreaElement | null>(null)
const mode = ref<'voice' | 'auto'>('voice')
const voiceId = ref<string | null>(null)
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
  voiceLabel: string
  languageLabel: string
} | null>(null)

let jobToken = 0
let alive = true

const samplePrompts = [
  {
    label: 'Welcome',
    text: 'Welcome to OmniVoice Studio. Everything you hear is generated locally, inside your own Docker container.',
  },
  {
    label: 'Narration',
    text: 'The train pulled out of the station just as the sun began to set. Somewhere ahead, the city lights were waiting.',
  },
  {
    label: 'Dialogue',
    text: 'Did you hear that? I could have sworn the house was empty. Let’s check the study one more time.',
  },
]

const selectedVoice = computed(
  () => store.voices.find((voice) => voice.id === voiceId.value) || null,
)

const effectiveLanguage = computed(
  () =>
    language.value ||
    (mode.value === 'voice' ? selectedVoice.value?.language : null) ||
    null,
)

const selectedLanguage = computed(
  () => store.languages.find((item) => item.id === language.value) || null,
)

const languageVariantIssue = computed(() => {
  const variant = selectedLanguage.value
  if (!variant?.requires_voice) return ''
  if (mode.value !== 'voice') {
    return `${variant.name} needs a trained voice profile. Auto voice cannot guarantee the accent.`
  }
  if (selectedVoice.value?.language !== variant.id) {
    return `Select a voice tagged ${variant.name}, or retrain/tag your voice with a matching reference clip.`
  }
  return ''
})

const charCount = computed(() => text.value.length)
const activeJobRunning = computed(() => isJobActive(activeJob.value))
const canGenerate = computed(
  () =>
    modelReady.value &&
    !languageVariantIssue.value &&
    text.value.trim().length > 0 &&
    (mode.value === 'auto' || Boolean(voiceId.value)),
)

const recent = computed(() => store.history.slice(0, 4))

watch(
  () => store.voices,
  (voices) => {
    if (!voices.length) {
      mode.value = 'auto'
      voiceId.value = null
      return
    }
    if (
      requestedVoiceId.value &&
      voices.some((voice) => voice.id === requestedVoiceId.value)
    ) {
      voiceId.value = requestedVoiceId.value
      mode.value = 'voice'
      requestedVoiceId.value = null
      return
    }
    if (!voiceId.value || !voices.some((voice) => voice.id === voiceId.value)) {
      voiceId.value = voices[0]?.id || null
      mode.value = 'voice'
    }
  },
  { immediate: true },
)

function useSample(prompt: { text: string }): void {
  text.value = prompt.text
}

function clearText(): void {
  text.value = ''
  error.value = ''
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
  if (mode.value === 'voice' && !voiceId.value) {
    error.value = 'Choose a trained voice or switch to Auto voice.'
    return
  }

  error.value = ''
  const token = ++jobToken

  try {
    const job = await api.submitTtsJob({
      text: text.value.trim(),
      mode: (mode.value === 'voice' ? 'voice' : 'auto') as TTSMode,
      voice_id: mode.value === 'voice' ? voiceId.value : null,
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
        voiceLabel:
          finished.result.voice_name ||
          (mode.value === 'voice'
            ? selectedVoice.value?.name || 'Trained voice'
            : 'Auto voice'),
        languageLabel: effectiveLanguage.value
          ? languageName(effectiveLanguage.value, store.languages)
          : 'Auto-detect',
      }
      activeJob.value = null
      await refreshHistory()
      toast(
        'success',
        'Speech generated',
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
        <h1 class="page-title">Give your words a voice.</h1>
        <p class="page-subtitle">
          Type anything, pick a trained voice, and generate speech locally.
          No cloud, no API keys, no audio leaving your machine.
        </p>
      </div>
      <RouterLink to="/voices" class="btn btn-secondary">
        <Mic2 :size="15" />
        Train a voice
      </RouterLink>
    </div>

    <div class="grid-2">
      <section class="card composer">
        <div class="card-head">
          <div>
            <div class="card-title">Script</div>
            <div class="card-sub">Up to 8,000 characters per generation.</div>
          </div>
          <button
            v-if="text"
            type="button"
            class="btn btn-ghost btn-sm"
            @click="clearText"
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
          spellcheck="true"
          @keydown.ctrl.enter.prevent="generate"
          @keydown.meta.enter.prevent="generate"
        />

        <TextAssist @insert="insertToken" />

        <div class="sample-prompts">
          <button
            v-for="prompt in samplePrompts"
            :key="prompt.label"
            type="button"
            class="chip"
            @click="useSample(prompt)"
          >
            <Plus :size="11" />
            {{ prompt.label }}
          </button>
        </div>

        <div class="composer-foot">
          <span class="composer-count">{{ charCount }} / 8000</span>
          <div class="row">
            <span class="field-hint">Ctrl / ⌘ + Enter</span>
            <button
              type="button"
              class="btn btn-primary btn-lg"
              :disabled="!canGenerate"
              @click="generate"
            >
              <ListPlus v-if="activeJobRunning" :size="16" />
              <Sparkles v-else :size="16" />
              {{ activeJobRunning ? 'Queue another' : 'Generate speech' }}
            </button>
          </div>
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
              <div class="card-title">Voice</div>
              <div class="card-sub">Use a trained profile or let OmniVoice choose.</div>
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
              Auto voice
            </button>
          </div>

          <template v-if="mode === 'voice'">
            <template v-if="store.voices.length">
              <select v-model="voiceId" class="select" style="margin-bottom: 12px">
                <option
                  v-for="voice in store.voices"
                  :key="voice.id"
                  :value="voice.id"
                >
                  {{ voice.name }}
                </option>
              </select>

              <div v-if="selectedVoice" class="voice-select-card">
                <div
                  class="voice-avatar"
                  :style="{ background: voiceGradient(selectedVoice.id + selectedVoice.name) }"
                >
                  {{ initials(selectedVoice.name) }}
                </div>
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

              <div class="row" style="margin-top: 10px; flex-wrap: wrap">
                <AudioButton
                  v-if="selectedVoice?.has_preview"
                  :src="api.previewUrl(selectedVoice.id, selectedVoice.preview_updated_at)"
                  label="Preview"
                />
                <RouterLink
                  :to="{ path: '/voices', query: { voice: selectedVoice?.id } }"
                  class="btn btn-ghost btn-sm"
                >
                  Manage voice
                  <ArrowRight :size="13" />
                </RouterLink>
              </div>
            </template>

            <div v-else class="empty-state" style="min-height: 160px">
              <div class="empty-visual" style="width: 52px; height: 52px; margin-bottom: 10px">
                <Mic2 :size="21" class="muted" />
              </div>
              <div class="empty-title">No trained voices yet</div>
              <div class="empty-text">
                Add a 3–10 second reference clip and reuse that voice forever.
              </div>
              <RouterLink to="/voices" class="btn btn-primary btn-sm" style="margin-top: 12px">
                <Mic2 :size="13" />
                Train your first voice
              </RouterLink>
            </div>
          </template>

          <div v-else class="voice-select-card">
            <div class="voice-avatar" style="background: linear-gradient(135deg, #8b5cf6, #4f46e5)">
              <Wand2 :size="18" />
            </div>
            <div class="voice-select-main">
              <div class="voice-select-name">Auto voice</div>
              <div class="voice-select-meta">
                OmniVoice picks a voice for the text and language.
              </div>
            </div>
          </div>
        </section>

        <section class="card card-pad">
          <div class="card-head">
            <div>
              <div class="card-title">Generation settings</div>
              <div class="card-sub">Language, pacing, quality, and output.</div>
            </div>
            <AudioLines :size="17" class="muted" />
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
      <div
        v-if="activeJob && activeJobRunning"
        class="card result-card"
      >
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
                    : 'Generating speech'
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
          <span>{{ activeJob.summary.text_preview || 'Speech generation' }}</span>
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
        :voice-label="result.voiceLabel"
        :language-label="result.languageLabel"
        title="Your speech"
      >
        <template #actions>
          <RouterLink to="/history" class="btn btn-ghost btn-sm">
            <Clock3 :size="13" />
            History
          </RouterLink>
        </template>
      </ResultCard>

      <div v-else class="card result-card">
        <div class="empty-state" style="min-height: 210px">
          <div class="empty-visual">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
          <div class="empty-title">Your generated speech will appear here</div>
          <div class="empty-text">
            Write a script, choose a voice, and press Generate. The audio is
            synthesized by the local OmniVoice engine and saved to your history.
          </div>
        </div>
      </div>
    </div>

    <section v-if="recent.length" class="card card-pad" style="margin-top: 20px">
      <div class="card-head">
        <div>
          <div class="card-title">Recent generations</div>
          <div class="card-sub">Stored in the local Docker volume.</div>
        </div>
        <RouterLink to="/history" class="btn btn-ghost btn-sm">
          View all
          <ArrowRight :size="13" />
        </RouterLink>
      </div>

      <div class="recent-list">
        <div v-for="item in recent" :key="item.id" class="recent-item">
          <div class="recent-main">
            <div class="recent-text">{{ truncate(item.text_preview, 110) }}</div>
            <div class="recent-meta">
              {{ item.voice_name || (item.mode === 'design' ? 'Designed voice' : 'Auto voice') }}
              · {{ formatTime(item.duration_seconds) }} · {{ formatDate(item.created_at) }}
            </div>
          </div>
          <AudioButton :src="api.outputUrl(item.id)" label="Play" />
        </div>
      </div>
    </section>
  </div>
</template>

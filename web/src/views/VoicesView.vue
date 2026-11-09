<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import {
  Ban,
  FileAudio2,
  Mic2,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
  X,
} from '@lucide/vue'
import AudioButton from '../components/AudioButton.vue'
import LanguageSelect from '../components/LanguageSelect.vue'
import Recorder from '../components/Recorder.vue'
import { api, getErrorMessage } from '../lib/api'
import {
  formatBytes,
  formatDate,
  formatTime,
  initials,
  languageName,
  voiceGradient,
} from '../lib/format'
import { isJobActive, waitForJob } from '../lib/jobs'
import { previewTextForLanguage } from '../lib/language'
import {
  modelReady,
  refreshVoices,
  store,
  upsertJob,
} from '../lib/store'
import { toast } from '../lib/toast'
import type { Job, SampleUpload, Voice } from '../lib/types'

const showForm = ref(false)
const editing = ref<Voice | null>(null)
const sampleMode = ref<'record' | 'upload'>('record')
const sample = ref<SampleUpload | null>(null)
const samplePreviewUrl = ref('')
const dragActive = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const formError = ref('')
const previewing = ref<string | null>(null)
const activeJob = ref<Job | null>(null)

const form = reactive({
  name: '',
  transcript: '',
  language: null as string | null,
  consent: false,
})

let jobToken = 0
let alive = true

const formTitle = computed(() =>
  editing.value ? 'Retrain voice' : 'Train a new voice',
)

const formSubtitle = computed(() =>
  editing.value
    ? 'Replace the reference clip, update the transcript, or both.'
    : 'Turn a short reference clip into a reusable voice profile.',
)

const trainingActive = computed(() => isJobActive(activeJob.value))
const trainingElapsed = computed(() =>
  Math.round(activeJob.value?.elapsed_seconds || 0),
)

const canSubmit = computed(
  () =>
    modelReady.value &&
    !trainingActive.value &&
    form.name.trim().length > 0 &&
    form.consent &&
    (Boolean(editing.value) || Boolean(sample.value)),
)

const sampleSize = computed(() =>
  sample.value ? formatBytes(sample.value.blob.size) : '',
)

function resetForm(): void {
  form.name = ''
  form.transcript = ''
  form.language = null
  form.consent = false
  sample.value = null
  sampleMode.value = 'record'
  formError.value = ''
  if (samplePreviewUrl.value) {
    URL.revokeObjectURL(samplePreviewUrl.value)
    samplePreviewUrl.value = ''
  }
  if (fileInput.value) fileInput.value.value = ''
}

async function scrollToForm(): Promise<void> {
  await nextTick()
  document.querySelector('.train-form')?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function openCreate(): void {
  if (trainingActive.value) {
    toast('info', 'Training in progress', 'Cancel or wait for the current job.')
    return
  }
  resetForm()
  editing.value = null
  showForm.value = true
  void scrollToForm()
}

function openRetrain(voice: Voice): void {
  if (trainingActive.value) {
    toast('info', 'Training in progress', 'Cancel or wait for the current job.')
    return
  }
  resetForm()
  editing.value = voice
  form.name = voice.name
  form.transcript = voice.transcript || ''
  form.language = voice.language
  form.consent = true
  showForm.value = true
  void scrollToForm()
}

function closeForm(): void {
  if (trainingActive.value) {
    toast('info', 'Training in progress', 'Cancel the job before closing the form.')
    return
  }
  showForm.value = false
  editing.value = null
  resetForm()
}

function handleRecorded(value: SampleUpload | null): void {
  sample.value = value
  formError.value = ''
  if (samplePreviewUrl.value) {
    URL.revokeObjectURL(samplePreviewUrl.value)
    samplePreviewUrl.value = ''
  }
  if (value) {
    samplePreviewUrl.value = URL.createObjectURL(value.blob)
  }
}

function acceptFile(file: File | undefined | null): void {
  if (!file) return
  const looksAudio =
    file.type.startsWith('audio/') ||
    /\.(wav|mp3|m4a|aac|ogg|opus|webm|flac)$/i.test(file.name)
  if (!looksAudio) {
    toast('error', 'Unsupported file', 'Choose a WAV, MP3, M4A, OGG, WebM, or FLAC file.')
    return
  }
  if (file.size > 50 * 1024 * 1024) {
    toast('error', 'File too large', 'The reference clip must be under 50 MB.')
    return
  }
  if (samplePreviewUrl.value) URL.revokeObjectURL(samplePreviewUrl.value)
  samplePreviewUrl.value = URL.createObjectURL(file)
  sample.value = { blob: file, filename: file.name }
  sampleMode.value = 'upload'
  formError.value = ''
}

function onFileInput(event: Event): void {
  const input = event.target as HTMLInputElement
  acceptFile(input.files?.[0])
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragActive.value = false
  acceptFile(event.dataTransfer?.files?.[0])
}

function clearSample(): void {
  sample.value = null
  if (samplePreviewUrl.value) {
    URL.revokeObjectURL(samplePreviewUrl.value)
    samplePreviewUrl.value = ''
  }
  if (fileInput.value) fileInput.value.value = ''
}

function setSampleMode(next: 'record' | 'upload'): void {
  if (sampleMode.value === next) return
  sampleMode.value = next
  clearSample()
}

async function submit(): Promise<void> {
  formError.value = ''
  if (trainingActive.value) return
  if (!form.name.trim()) {
    formError.value = 'Give this voice a name.'
    return
  }
  if (!form.consent) {
    formError.value = 'Confirm that you have permission to clone this voice.'
    return
  }
  if (!editing.value && !sample.value) {
    formError.value = 'Record or upload a reference clip first.'
    return
  }
  if (!modelReady.value) {
    formError.value = 'The model is still warming up. Try again in a moment.'
    return
  }

  const isRetrain = Boolean(editing.value)
  const token = ++jobToken

  try {
    const job =
      isRetrain && editing.value
        ? await api.submitRetrainJob(editing.value.id, {
            name: form.name.trim(),
            transcript: form.transcript.trim(),
            language: form.language,
            audio: sample.value?.blob || null,
            filename: sample.value?.filename,
          })
        : sample.value
          ? await api.submitVoiceJob({
              name: form.name.trim(),
              transcript: form.transcript.trim(),
              language: form.language,
              audio: sample.value.blob,
              filename: sample.value.filename,
            })
          : null

    if (!job) {
      throw new Error('A reference clip is required')
    }
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

    if (finished.status === 'completed') {
      const voiceId = finished.result?.id || editing.value?.id
      if (!voiceId) {
        activeJob.value = null
        formError.value = 'Training completed but no voice id was returned.'
        return
      }
      const voiceName = finished.result?.name || form.name
      await refreshVoices()
      const voice = store.voices.find((item) => item.id === voiceId) || null
      activeJob.value = null
      toast(
        'success',
        isRetrain ? 'Voice retrained' : 'Voice trained',
        `${voiceName} is ready to use in the Studio.`,
      )
      showForm.value = false
      editing.value = null
      resetForm()
      if (voice) void generatePreview(voice)
    } else if (finished.status === 'cancelled') {
      activeJob.value = null
      formError.value = 'Training cancelled.'
      toast('info', 'Training cancelled', 'The job was removed or stopped.')
    } else {
      activeJob.value = null
      formError.value = finished.error || 'Training failed.'
      toast('error', 'Training failed', formError.value)
    }
  } catch (error) {
    if (token === jobToken) {
      activeJob.value = null
      formError.value = getErrorMessage(error)
      toast('error', 'Training failed', formError.value)
    }
  }
}

async function cancelTraining(): Promise<void> {
  if (!activeJob.value) return
  try {
    const job = await api.cancelJob(activeJob.value.id)
    activeJob.value = job
    upsertJob(job)
    toast(
      'info',
      job.status === 'cancelled' ? 'Training cancelled' : 'Cancellation requested',
      job.status === 'cancelled'
        ? 'The queued job was removed.'
        : 'The worker will stop after the current step.',
    )
  } catch (error) {
    toast('error', 'Could not cancel training', getErrorMessage(error))
  }
}

async function generatePreview(voice: Voice): Promise<void> {
  if (previewing.value) return
  previewing.value = voice.id
  try {
    const job = await api.submitPreviewJob(
      voice.id,
      previewTextForLanguage(voice.language),
    )
    upsertJob(job)
    const finished = await waitForJob(job.id, undefined, () => !alive)
    if (!alive) return
    if (finished.status === 'completed') {
      await refreshVoices()
      toast('success', 'Preview ready', `Generated a sample with ${voice.name}.`)
    } else if (finished.status === 'cancelled') {
      toast('info', 'Preview cancelled', 'The job was removed or stopped.')
    } else {
      toast(
        'error',
        'Could not generate preview',
        finished.error || 'Preview failed',
      )
    }
  } catch (error) {
    toast('error', 'Could not generate preview', getErrorMessage(error))
  } finally {
    previewing.value = null
  }
}

function previewSrc(voice: Voice): string {
  return voice.has_preview
    ? api.previewUrl(voice.id, voice.preview_updated_at)
    : ''
}

async function rename(voice: Voice): Promise<void> {
  if (trainingActive.value) {
    toast('info', 'Training in progress', 'Cancel or wait for the current job.')
    return
  }
  const nextName = window.prompt('Rename voice', voice.name)?.trim()
  if (!nextName || nextName === voice.name) return
  try {
    await api.renameVoice(voice.id, nextName)
    await refreshVoices()
    toast('success', 'Voice renamed', `Now called ${nextName}.`)
  } catch (error) {
    toast('error', 'Rename failed', getErrorMessage(error))
  }
}

async function remove(voice: Voice): Promise<void> {
  if (trainingActive.value) {
    toast('info', 'Training in progress', 'Cancel or wait for the current job.')
    return
  }
  if (!window.confirm(`Delete "${voice.name}" and its reference audio?`)) return
  try {
    await api.deleteVoice(voice.id)
    await refreshVoices()
    toast('success', 'Voice deleted', `${voice.name} was removed.`)
  } catch (error) {
    toast('error', 'Delete failed', getErrorMessage(error))
  }
}

onBeforeUnmount(() => {
  alive = false
  jobToken += 1
  if (samplePreviewUrl.value) URL.revokeObjectURL(samplePreviewUrl.value)
})
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Your voices.</h1>
        <p class="page-subtitle">
          OmniVoice is a zero-shot model: a clean 3–10 second reference clip is
          enough to create a reusable voice profile. No gradient training, no
          fine-tuning, no cloud upload.
        </p>
      </div>
      <button
        type="button"
        class="btn btn-primary"
        :disabled="trainingActive"
        @click="openCreate"
      >
        <Plus :size="15" />
        Train voice
      </button>
    </div>

    <div :class="showForm ? 'train-layout' : ''">
      <div class="stack">
        <div v-if="store.voices.length" class="voice-grid">
          <article
            v-for="voice in store.voices"
            :key="voice.id"
            class="card voice-card"
          >
            <div class="voice-card-head">
              <div
                class="voice-avatar"
                :style="{ background: voiceGradient(voice.id + voice.name) }"
              >
                {{ initials(voice.name) }}
              </div>
              <div class="voice-card-main">
                <div class="voice-name">{{ voice.name }}</div>
                <div class="voice-meta">
                  <span>{{ formatTime(voice.duration_seconds) }} reference</span>
                  <span>{{ languageName(voice.language, store.languages) }}</span>
                  <span>{{ formatDate(voice.updated_at) }}</span>
                </div>
              </div>
              <span class="badge mint">Trained</span>
            </div>

            <div v-if="voice.transcript" class="voice-transcript">
              “{{ voice.transcript }}”
            </div>

            <div class="voice-actions">
              <AudioButton
                :src="api.referenceUrl(voice.id)"
                label="Reference"
              />
              <AudioButton
                v-if="previewSrc(voice)"
                :src="previewSrc(voice)"
                label="Preview"
              />
              <button
                v-else
                type="button"
                class="btn btn-secondary btn-sm"
                :disabled="previewing !== null || !modelReady"
                @click="generatePreview(voice)"
              >
                <span v-if="previewing === voice.id" class="spinner" />
                <Wand2 v-else :size="13" />
                {{ previewing === voice.id ? 'Previewing…' : 'Preview' }}
              </button>
            </div>

            <div class="row-between">
              <div class="row" style="gap: 2px">
                <button
                  type="button"
                  class="icon-btn"
                  title="Retrain voice"
                  :disabled="trainingActive"
                  @click="openRetrain(voice)"
                >
                  <RefreshCw :size="15" />
                </button>
                <button
                  type="button"
                  class="icon-btn"
                  title="Rename voice"
                  :disabled="trainingActive"
                  @click="rename(voice)"
                >
                  <Pencil :size="15" />
                </button>
                <button
                  type="button"
                  class="icon-btn danger"
                  title="Delete voice"
                  :disabled="trainingActive"
                  @click="remove(voice)"
                >
                  <Trash2 :size="15" />
                </button>
              </div>
              <RouterLink
                :to="{ path: '/', query: { voice: voice.id } }"
                class="btn btn-ghost btn-sm"
              >
                Use in Studio
              </RouterLink>
            </div>
          </article>
        </div>

        <div v-else-if="!showForm" class="card card-pad">
          <div class="empty-state" style="min-height: 300px">
            <div class="empty-visual" style="width: 64px; height: 64px">
              <Mic2 :size="25" class="muted" />
            </div>
            <div class="empty-title">Train your first voice</div>
            <div class="empty-text">
              Record a short sample or upload a clean clip. OmniVoice will encode
              it into a reusable voice profile stored in your local data volume.
            </div>
            <button type="button" class="btn btn-primary btn-sm" style="margin-top: 14px" @click="openCreate">
              <Mic2 :size="13" />
              Get started
            </button>
          </div>
        </div>

        <div v-if="store.voices.length" class="card card-pad">
          <div class="card-head" style="margin-bottom: 10px">
            <div>
              <div class="card-title">Tips for a great clone</div>
              <div class="card-sub">The reference clip is the biggest quality lever.</div>
            </div>
          </div>
          <div class="tips-card">
            <div class="tips-title">
              <Sparkles :size="14" />
              Reference audio checklist
            </div>
            <ul class="tips-list">
              <li>Use 3–10 seconds of clean, single-speaker audio.</li>
              <li>Avoid background music, echo, and heavy room noise.</li>
              <li>Speak naturally — the transcript should match the clip exactly.</li>
              <li>Use the same language as the speech you want to generate.</li>
            </ul>
          </div>
        </div>
      </div>

      <aside v-if="showForm" class="card train-form">
        <div class="card-head">
          <div>
            <div class="card-title">{{ formTitle }}</div>
            <div class="card-sub">{{ formSubtitle }}</div>
          </div>
          <button
            type="button"
            class="icon-btn"
            title="Close"
            :disabled="trainingActive"
            @click="closeForm"
          >
            <X :size="16" />
          </button>
        </div>

        <div class="stack">
          <div class="field">
            <label class="field-label">Voice name</label>
            <input
              v-model="form.name"
              class="input"
              maxlength="60"
              placeholder="e.g. Alice, Narrator, My voice"
            />
          </div>

          <div class="field">
            <div class="field-label">
              <span>Reference audio</span>
              <span v-if="sample" class="badge">{{ sampleSize }}</span>
            </div>

            <div class="tabs" style="margin-bottom: 10px">
              <button
                type="button"
                class="tab"
                :class="{ active: sampleMode === 'record' }"
                @click="setSampleMode('record')"
              >
                Record
              </button>
              <button
                type="button"
                class="tab"
                :class="{ active: sampleMode === 'upload' }"
                @click="setSampleMode('upload')"
              >
                Upload
              </button>
            </div>

            <Recorder
              v-if="sampleMode === 'record'"
              @update="handleRecorded"
            />

            <template v-else>
              <input
                ref="fileInput"
                type="file"
                accept="audio/*,.wav,.mp3,.m4a,.ogg,.opus,.webm,.flac"
                class="sr-only"
                @change="onFileInput"
              />
              <div
                v-if="!sample"
                class="dropzone"
                :class="{ dragging: dragActive }"
                role="button"
                tabindex="0"
                @click="fileInput?.click()"
                @keydown.enter.prevent="fileInput?.click()"
                @dragover.prevent="dragActive = true"
                @dragleave.prevent="dragActive = false"
                @drop.prevent="onDrop"
              >
                <div class="dropzone-icon"><Upload :size="19" /></div>
                <div class="dropzone-title">Drop an audio file here</div>
                <div class="dropzone-text">
                  WAV, MP3, M4A, OGG, WebM, or FLAC · up to 50 MB
                </div>
              </div>
              <div v-else class="stack-sm">
                <div class="sample-file">
                  <FileAudio2 :size="18" class="muted" />
                  <div class="sample-file-main">
                    <div class="sample-file-name">{{ sample.filename }}</div>
                    <div class="sample-file-meta">{{ sampleSize }}</div>
                  </div>
                  <button type="button" class="icon-btn danger" @click="clearSample">
                    <Trash2 :size="14" />
                  </button>
                </div>
                <audio
                  v-if="samplePreviewUrl"
                  :src="samplePreviewUrl"
                  controls
                  style="width: 100%; height: 38px"
                />
              </div>
            </template>

            <div
              v-if="editing && !sample"
              class="sample-file"
              style="margin-top: 4px"
            >
              <FileAudio2 :size="17" class="muted" />
              <div class="sample-file-main">
                <div class="sample-file-name">Using the existing reference</div>
                <div class="sample-file-meta">
                  {{ formatTime(editing.duration_seconds) }} ·
                  {{ languageName(editing.language, store.languages) }}
                </div>
              </div>
              <AudioButton :src="api.referenceUrl(editing.id)" label="Listen" />
            </div>
          </div>

          <div class="field">
            <label class="field-label">
              <span>Transcript</span>
              <span class="muted-2" style="font-weight: 500; text-transform: none">
                optional
              </span>
            </label>
            <textarea
              v-model="form.transcript"
              class="textarea"
              rows="3"
              placeholder="Exactly what is said in the clip…"
            />
            <span class="field-hint">
              Leave blank to auto-transcribe with Whisper. Typing it yourself is
              faster and improves cloning quality.
            </span>
          </div>

          <div class="field">
            <label class="field-label">Language</label>
            <LanguageSelect
              v-model="form.language"
              :languages="store.languages"
            />
            <span class="field-hint">
              Use the language spoken in the reference clip.
            </span>
            <span
              v-if="form.language?.startsWith('pt')"
              class="field-hint"
            >
              OmniVoice has one Portuguese language ID. The reference clip
              controls the accent: use a Portugal reference for Portuguese
              (Portugal).
            </span>
          </div>

          <label class="checkbox">
            <input v-model="form.consent" type="checkbox" />
            <span>
              I have permission to use this person’s voice, and I will not use it
              for impersonation, fraud, or harassment.
            </span>
          </label>

          <p v-if="formError" class="field-error">{{ formError }}</p>

          <div class="form-actions">
            <button
              type="button"
              class="btn btn-primary btn-block"
              :disabled="!canSubmit"
              @click="submit"
            >
              <span v-if="trainingActive" class="spinner" />
              <Sparkles v-else :size="15" />
              {{
                trainingActive
                  ? `Training · ${trainingElapsed}s`
                  : editing
                    ? 'Retrain voice'
                    : 'Train voice'
              }}
            </button>
            <button
              v-if="trainingActive"
              type="button"
              class="btn btn-danger"
              :disabled="activeJob?.status === 'cancelling'"
              @click="cancelTraining"
            >
              <Ban :size="14" />
              Cancel
            </button>
          </div>

          <div
            v-if="trainingActive && activeJob"
            class="banner loading"
            style="margin: 0"
          >
            <div class="banner-icon">
              <span v-if="activeJob.status === 'running'" class="spinner accent" />
              <Ban v-else :size="17" />
            </div>
            <div class="banner-body">
              <div class="banner-title">
                {{
                  activeJob.status === 'queued'
                    ? 'Queued for training'
                    : activeJob.status === 'cancelling'
                      ? 'Cancelling training'
                      : 'Encoding the reference voice'
                }}
              </div>
              <div class="banner-text">
                {{ activeJob.message }}
                <span v-if="activeJob.queue_position">
                  · position #{{ activeJob.queue_position }}
                </span>
              </div>
              <div class="progress-track" style="margin-top: 8px">
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
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

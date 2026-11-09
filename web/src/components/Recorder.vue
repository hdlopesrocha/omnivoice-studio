<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Mic, RotateCcw, Square } from '@lucide/vue'
import type { SampleUpload } from '../lib/types'

const emit = defineEmits<{
  update: [value: SampleUpload | null]
}>()

const MAX_SECONDS = 20

const recording = ref(false)
const elapsed = ref(0)
const level = ref(0)
const error = ref('')
const blob = ref<Blob | null>(null)
const blobUrl = ref('')

let mediaRecorder: MediaRecorder | null = null
let stream: MediaStream | null = null
let chunks: Blob[] = []
let timer: number | null = null
let animationFrame: number | null = null
let audioContext: AudioContext | null = null
let analyser: AnalyserNode | null = null
let startedAt = 0

const timerLabel = computed(() => `${elapsed.value.toFixed(1)}s`)
const levelBars = computed(() =>
  Array.from({ length: 14 }, (_, index) => {
    const shape = 0.35 + ((index * 7) % 10) / 14
    return Math.max(3, Math.round(4 + level.value * 22 * shape))
  }),
)

function pickMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/ogg;codecs=opus',
    'audio/webm',
    'audio/mp4',
  ]
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function filenameFor(mimeType: string): string {
  if (mimeType.includes('mp4')) return 'recording.m4a'
  if (mimeType.includes('ogg')) return 'recording.ogg'
  return 'recording.webm'
}

function stopTracks(): void {
  stream?.getTracks().forEach((track) => track.stop())
  stream = null
}

function cleanupMeter(): void {
  if (animationFrame !== null) {
    cancelAnimationFrame(animationFrame)
    animationFrame = null
  }
  if (audioContext) {
    void audioContext.close()
    audioContext = null
  }
  analyser = null
}

function startMeter(source: MediaStream): void {
  audioContext = new AudioContext()
  analyser = audioContext.createAnalyser()
  analyser.fftSize = 256
  const input = audioContext.createMediaStreamSource(source)
  input.connect(analyser)
  const data = new Uint8Array(analyser.fftSize)

  const tick = () => {
    if (!analyser) return
    analyser.getByteTimeDomainData(data)
    let sum = 0
    for (const value of data) {
      const normalized = (value - 128) / 128
      sum += normalized * normalized
    }
    const rms = Math.sqrt(sum / data.length)
    level.value = Math.min(1, rms * 4.2)
    animationFrame = requestAnimationFrame(tick)
  }
  tick()
}

async function start(): Promise<void> {
  error.value = ''
  if (!navigator.mediaDevices?.getUserMedia) {
    error.value = 'Microphone recording is not available in this browser.'
    return
  }

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    const mimeType = pickMimeType()
    mediaRecorder = new MediaRecorder(
      stream,
      mimeType ? { mimeType } : undefined,
    )
    chunks = []
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data)
    }
    mediaRecorder.onstop = () => {
      const type = mediaRecorder?.mimeType || mimeType || 'audio/webm'
      const recordingBlob = new Blob(chunks, { type })
      if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
      blob.value = recordingBlob
      blobUrl.value = URL.createObjectURL(recordingBlob)
      emit('update', {
        blob: recordingBlob,
        filename: filenameFor(type),
        seconds: elapsed.value,
      })
    }

    mediaRecorder.start(250)
    startedAt = Date.now()
    elapsed.value = 0
    recording.value = true
    startMeter(stream)
    timer = window.setInterval(() => {
      elapsed.value = (Date.now() - startedAt) / 1000
      if (elapsed.value >= MAX_SECONDS) stop()
    }, 100)
  } catch (err) {
    error.value =
      err instanceof Error
        ? `Could not start the microphone: ${err.message}`
        : 'Could not start the microphone.'
    stopTracks()
    cleanupMeter()
  }
}

function stop(): void {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
  recording.value = false
  cleanupMeter()
  stopTracks()
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }
  mediaRecorder = null
}

function reset(): void {
  stop()
  if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
  blob.value = null
  blobUrl.value = ''
  elapsed.value = 0
  level.value = 0
  error.value = ''
  emit('update', null)
}

onBeforeUnmount(() => {
  stop()
  if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
})
</script>

<template>
  <div class="recorder">
    <div v-if="!blobUrl" class="recorder-stage">
      <div class="recorder-mic" :class="{ live: recording }">
        <Mic :size="21" />
      </div>
      <div class="recorder-main">
        <div class="recorder-title">
          {{ recording ? 'Recording your voice…' : 'Record a reference sample' }}
        </div>
        <div class="recorder-sub">
          {{ recording ? 'Read naturally, then stop.' : '3–10 seconds works best. Up to 20 seconds.' }}
        </div>
        <div class="recorder-levels" aria-hidden="true">
          <span
            v-for="(height, index) in levelBars"
            :key="index"
            :style="{ height: `${recording ? height : 4}px` }"
          />
        </div>
      </div>
      <div class="row">
        <span v-if="recording" class="recorder-timer">{{ timerLabel }}</span>
        <button
          v-if="!recording"
          type="button"
          class="btn btn-primary btn-sm"
          @click="start"
        >
          <Mic :size="14" />
          Record
        </button>
        <button
          v-else
          type="button"
          class="btn btn-danger btn-sm"
          @click="stop"
        >
          <Square :size="12" fill="currentColor" />
          Stop
        </button>
      </div>
    </div>

    <div v-else class="stack-sm">
      <div class="sample-file">
        <div class="sample-file-main">
          <div class="sample-file-name">Recorded sample</div>
          <div class="sample-file-meta">{{ timerLabel }} captured</div>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" @click="reset">
          <RotateCcw :size="13" />
          Re-record
        </button>
      </div>
      <div class="recorder-preview">
        <audio :src="blobUrl" controls preload="metadata" />
      </div>
    </div>

    <p v-if="error" class="field-error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Download, Pause, Play } from '@lucide/vue'
import { formatTime } from '../lib/format'

const props = withDefaults(
  defineProps<{
    src: string
    title?: string
    downloadUrl?: string
    compact?: boolean
  }>(),
  {
    title: 'Audio',
    downloadUrl: '',
    compact: false,
  },
)

const audio = ref<HTMLAudioElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const wrap = ref<HTMLElement | null>(null)
const playing = ref(false)
const current = ref(0)
const duration = ref(0)
const peaks = ref<number[]>([])
const loading = ref(false)
const failed = ref(false)

let audioContext: AudioContext | null = null
let observer: ResizeObserver | null = null
let decodedFor = ''

function fallbackPeaks(count: number): number[] {
  return Array.from({ length: count }, (_, index) => {
    const wave = Math.sin(index * 0.55) * 0.35 + Math.sin(index * 0.17) * 0.2
    return Math.max(0.08, Math.min(0.95, 0.42 + wave))
  })
}

async function loadWaveform(): Promise<void> {
  if (!props.src) {
    peaks.value = []
    duration.value = 0
    current.value = 0
    return
  }
  if (decodedFor === props.src) return
  decodedFor = props.src
  loading.value = true
  failed.value = false
  peaks.value = []
  current.value = 0
  duration.value = 0

  try {
    const response = await fetch(props.src)
    if (!response.ok) throw new Error('Could not load audio')
    const buffer = await response.arrayBuffer()
    audioContext ??= new AudioContext()
    const decoded = await audioContext.decodeAudioData(buffer.slice(0))
    const channel = decoded.getChannelData(0)
    const barCount = props.compact ? 64 : 132
    const block = Math.max(1, Math.floor(channel.length / barCount))
    const raw: number[] = []
    for (let bar = 0; bar < barCount; bar += 1) {
      let peak = 0
      const start = bar * block
      const step = Math.max(1, Math.floor(block / 180))
      for (let offset = 0; offset < block; offset += step) {
        const value = Math.abs(channel[start + offset] || 0)
        if (value > peak) peak = value
      }
      raw.push(peak)
    }
    const max = Math.max(...raw, 0.0001)
    peaks.value = raw.map((value) => Math.max(0.07, value / max))
    duration.value = decoded.duration
    await nextTick()
    draw()
  } catch {
    failed.value = true
    peaks.value = fallbackPeaks(props.compact ? 64 : 132)
    await nextTick()
    draw()
  } finally {
    loading.value = false
  }
}

function draw(): void {
  const element = canvas.value
  if (!element) return
  const width = element.clientWidth
  const height = element.clientHeight
  if (!width || !height) return

  const dpr = window.devicePixelRatio || 1
  element.width = Math.round(width * dpr)
  element.height = Math.round(height * dpr)
  const context = element.getContext('2d')
  if (!context) return
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, width, height)

  const count = peaks.value.length || 1
  const gap = props.compact ? 1.5 : 2
  const barWidth = Math.max(1, (width - gap * (count - 1)) / count)
  const progress = duration.value > 0 ? current.value / duration.value : 0

  for (let index = 0; index < count; index += 1) {
    const x = index * (barWidth + gap)
    const amplitude = peaks.value[index] ?? 0.18
    const barHeight = Math.max(2, amplitude * (height - 4))
    const y = (height - barHeight) / 2
    const played = (index + 1) / count <= progress
    context.fillStyle = played ? '#ff7a59' : 'rgba(255, 255, 255, 0.15)'
    context.beginPath()
    const radius = Math.min(barWidth / 2, 2)
    context.roundRect(x, y, barWidth, barHeight, radius)
    context.fill()
  }
}

function onTimeUpdate(): void {
  if (!audio.value) return
  current.value = audio.value.currentTime
  if (Number.isFinite(audio.value.duration) && audio.value.duration > 0) {
    duration.value = audio.value.duration
  }
  draw()
}

function onLoadedMetadata(): void {
  if (!audio.value) return
  if (Number.isFinite(audio.value.duration) && audio.value.duration > 0) {
    duration.value = audio.value.duration
    draw()
  }
}

async function toggle(): Promise<void> {
  const element = audio.value
  if (!element || !props.src) return
  if (element.paused) {
    try {
      await element.play()
    } catch {
      failed.value = true
    }
  } else {
    element.pause()
  }
}

function onPlay(): void {
  playing.value = true
}

function onPause(): void {
  playing.value = false
  draw()
}

function onEnded(): void {
  playing.value = false
  current.value = 0
  draw()
}

function seek(event: MouseEvent): void {
  const element = audio.value
  const target = event.currentTarget as HTMLElement
  if (!element || !duration.value) return
  const rect = target.getBoundingClientRect()
  const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
  element.currentTime = ratio * duration.value
  current.value = element.currentTime
  draw()
}

function reset(): void {
  if (audio.value) {
    audio.value.pause()
    audio.value.currentTime = 0
  }
  playing.value = false
  current.value = 0
  duration.value = 0
  peaks.value = []
  failed.value = false
  decodedFor = ''
}

watch(
  () => props.src,
  async () => {
    reset()
    await nextTick()
    await loadWaveform()
  },
  { immediate: true },
)

onMounted(() => {
  if (wrap.value) {
    observer = new ResizeObserver(() => draw())
    observer.observe(wrap.value)
  }
  draw()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  if (audio.value) audio.value.pause()
  if (audioContext) {
    void audioContext.close()
    audioContext = null
  }
})
</script>

<template>
  <div class="wave-player" :class="{ compact }">
    <button
      type="button"
      class="play-button"
      :disabled="!src || loading"
      :aria-label="playing ? 'Pause audio' : 'Play audio'"
      @click="toggle"
    >
      <span v-if="loading" class="spinner" />
      <Pause v-else-if="playing" :size="compact ? 15 : 19" fill="currentColor" />
      <Play
        v-else
        :size="compact ? 15 : 19"
        fill="currentColor"
        style="margin-left: 2px"
      />
    </button>

    <div class="wave-main">
      <div class="wave-header">
        <span class="wave-title">{{ title }}</span>
        <span class="wave-time">{{ formatTime(current) }} / {{ formatTime(duration) }}</span>
      </div>
      <div
        ref="wrap"
        class="wave-canvas-wrap"
        :class="{ compact }"
        @click="seek"
      >
        <canvas ref="canvas" />
      </div>
    </div>

    <div class="wave-actions">
      <a
        v-if="downloadUrl"
        class="icon-btn"
        :href="downloadUrl"
        download
        aria-label="Download audio"
      >
        <Download :size="16" />
      </a>
    </div>

    <audio
      ref="audio"
      :src="src"
      preload="metadata"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @play="onPlay"
      @pause="onPause"
      @ended="onEnded"
    />
  </div>
</template>

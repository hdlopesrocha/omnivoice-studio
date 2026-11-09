<script setup lang="ts">
import { computed } from 'vue'
import type { AudioFormat, Language } from '../lib/types'
import LanguageSelect from './LanguageSelect.vue'

defineProps<{
  languages: Language[]
}>()

const language = defineModel<string | null>('language', { default: null })
const speed = defineModel<number>('speed', { default: 1 })
const numStep = defineModel<number>('numStep', { default: 32 })
const format = defineModel<AudioFormat>('format', { default: 'wav' })

const qualityOptions = [16, 32, 48]
const formatOptions: AudioFormat[] = ['wav', 'mp3', 'flac']

const rangeStyle = computed<Record<string, string>>(() => {
  const percent = ((speed.value - 0.5) / 1.5) * 100
  return { '--range-fill': `${Math.max(0, Math.min(100, percent))}%` }
})
</script>

<template>
  <div class="settings-grid">
    <div class="field field-full">
      <label class="field-label">Language</label>
      <LanguageSelect v-model="language" :languages="languages" />
      <span class="field-hint">
        Auto-detect works well for most text. Pick a language for a specific accent.
      </span>
    </div>

    <div class="field field-full">
      <label class="field-label">
        <span>Speed</span>
        <span class="quality-value">{{ speed.toFixed(2) }}×</span>
      </label>
      <input
        v-model.number="speed"
        class="range"
        type="range"
        min="0.5"
        max="2"
        step="0.05"
        :style="rangeStyle"
      />
      <span class="field-hint">1.00× is natural. Lower is slower, higher is faster.</span>
    </div>

    <div class="field">
      <label class="field-label">Quality</label>
      <div class="segmented">
        <button
          v-for="steps in qualityOptions"
          :key="steps"
          type="button"
          class="segment"
          :class="{ active: numStep === steps }"
          @click="numStep = steps"
        >
          {{ steps }} steps
        </button>
      </div>
      <span class="field-hint">More steps = better quality, slower generation.</span>
    </div>

    <div class="field">
      <label class="field-label">Format</label>
      <div class="segmented">
        <button
          v-for="option in formatOptions"
          :key="option"
          type="button"
          class="segment"
          :class="{ active: format === option }"
          @click="format = option"
        >
          {{ option.toUpperCase() }}
        </button>
      </div>
      <span class="field-hint">WAV is lossless. MP3 and FLAC are smaller downloads.</span>
    </div>
  </div>
</template>

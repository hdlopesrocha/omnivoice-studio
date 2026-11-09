<script setup lang="ts">
import { computed } from 'vue'
import {
  Clock3,
  FileAudio2,
  Gauge,
  Languages,
  Sparkles,
  UserRound,
} from '@lucide/vue'
import { api } from '../lib/api'
import { formatRtf, formatTime } from '../lib/format'
import WavePlayer from './WavePlayer.vue'

const props = withDefaults(
  defineProps<{
    src: string
    outputId?: string
    duration?: number
    rtf?: number | null
    format?: string
    voiceLabel?: string
    languageLabel?: string
    title?: string
    subtitle?: string
  }>(),
  {
    outputId: '',
    duration: 0,
    rtf: null,
    format: 'wav',
    voiceLabel: '',
    languageLabel: '',
    title: 'Generated speech',
    subtitle: 'Ready to play, download, or find again in History.',
  },
)

const downloadUrl = computed(() =>
  props.outputId ? api.outputUrl(props.outputId, true) : '',
)
</script>

<template>
  <div class="card result-card">
    <div class="result-head">
      <div>
        <div class="result-title">
          <Sparkles :size="15" class="text-accent" />
          {{ title }}
        </div>
        <div class="card-sub">{{ subtitle }}</div>
      </div>
      <slot name="actions" />
    </div>

    <WavePlayer
      :src="src"
      :download-url="downloadUrl"
      :title="voiceLabel || 'Generated audio'"
    />

    <div class="result-meta">
      <span class="meta-item">
        <Clock3 :size="12" />
        <strong>{{ formatTime(duration) }}</strong> audio
      </span>
      <span class="meta-item">
        <Gauge :size="12" />
        RTF <strong>{{ formatRtf(rtf) }}</strong>
      </span>
      <span class="meta-item">
        <FileAudio2 :size="12" />
        <strong>{{ format.toUpperCase() }}</strong>
      </span>
      <span v-if="voiceLabel" class="meta-item">
        <UserRound :size="12" />
        <strong>{{ voiceLabel }}</strong>
      </span>
      <span v-if="languageLabel" class="meta-item">
        <Languages :size="12" />
        <strong>{{ languageLabel }}</strong>
      </span>
    </div>
  </div>
</template>

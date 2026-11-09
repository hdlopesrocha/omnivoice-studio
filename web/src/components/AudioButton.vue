<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Pause, Play } from '@lucide/vue'

const props = withDefaults(
  defineProps<{
    src: string
    label?: string
    playingLabel?: string
  }>(),
  {
    label: 'Play',
    playingLabel: 'Pause',
  },
)

const audio = ref<HTMLAudioElement | null>(null)
const playing = ref(false)

async function toggle(): Promise<void> {
  const element = audio.value
  if (!element) return
  if (element.paused) {
    try {
      await element.play()
    } catch {
      playing.value = false
    }
  } else {
    element.pause()
  }
}

watch(
  () => props.src,
  () => {
    if (audio.value) {
      audio.value.pause()
      audio.value.currentTime = 0
    }
    playing.value = false
  },
)

onBeforeUnmount(() => {
  if (audio.value) audio.value.pause()
})
</script>

<template>
  <button type="button" class="btn btn-secondary btn-sm" @click="toggle">
    <Pause v-if="playing" :size="13" fill="currentColor" />
    <Play v-else :size="13" fill="currentColor" />
    {{ playing ? playingLabel : label }}
  </button>
  <audio
    ref="audio"
    :src="src"
    preload="none"
    @play="playing = true"
    @pause="playing = false"
    @ended="playing = false"
  />
</template>

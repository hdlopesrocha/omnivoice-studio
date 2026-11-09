<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { Check, Copy } from '@lucide/vue'

const props = withDefaults(
  defineProps<{
    code: string
    label?: string
  }>(),
  {
    label: 'Shell',
  },
)

const copied = ref(false)
let resetTimer: number | null = null

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.code)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = props.code
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    textarea.remove()
  }
  copied.value = true
  if (resetTimer !== null) window.clearTimeout(resetTimer)
  resetTimer = window.setTimeout(() => {
    copied.value = false
  }, 1800)
}

onBeforeUnmount(() => {
  if (resetTimer !== null) window.clearTimeout(resetTimer)
})
</script>

<template>
  <div class="code-block">
    <div class="code-head">
      <span>{{ label }}</span>
      <button type="button" class="btn btn-ghost btn-sm" @click="copy">
        <Check v-if="copied" :size="12" />
        <Copy v-else :size="12" />
        {{ copied ? 'Copied' : 'Copy' }}
      </button>
    </div>
    <pre class="code-content"><code>{{ code }}</code></pre>
  </div>
</template>

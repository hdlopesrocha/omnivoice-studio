<script setup lang="ts">
const emit = defineEmits<{
  insert: [token: string]
}>()

const nonVerbal = [
  { token: '[laughter]', label: 'laughter' },
  { token: '[sigh]', label: 'sigh' },
  { token: '[confirmation-en]', label: 'confirmation' },
  { token: '[question-en]', label: 'question' },
  { token: '[question-ah]', label: 'question ah' },
  { token: '[question-oh]', label: 'question oh' },
  { token: '[question-ei]', label: 'question ei' },
  { token: '[question-yi]', label: 'question yi' },
  { token: '[surprise-ah]', label: 'surprise ah' },
  { token: '[surprise-oh]', label: 'surprise oh' },
  { token: '[surprise-wa]', label: 'surprise wa' },
  { token: '[surprise-yo]', label: 'surprise yo' },
  { token: '[dissatisfaction-hnn]', label: 'dissatisfaction' },
]

const pronunciation = [
  { token: '[B EY1 S]', label: 'English phonemes' },
  { token: 'ZHE2', label: 'pinyin tone' },
  { token: 'SHE2', label: 'pinyin tone 2' },
]
</script>

<template>
  <div class="text-assist">
    <div class="text-assist-group">
      <span class="text-assist-label">Non-verbal</span>
      <button
        v-for="item in nonVerbal"
        :key="item.token"
        type="button"
        class="chip"
        :title="item.token"
        @click="emit('insert', item.token)"
      >
        {{ item.label }}
      </button>
    </div>
    <div class="text-assist-group">
      <span class="text-assist-label">Pronunciation</span>
      <button
        v-for="item in pronunciation"
        :key="item.token"
        type="button"
        class="chip"
        :title="item.token"
        @click="emit('insert', item.token)"
      >
        {{ item.label }}
      </button>
    </div>
  </div>
</template>

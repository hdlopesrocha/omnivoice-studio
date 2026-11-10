<script setup lang="ts">
import { computed, ref } from 'vue'

const emit = defineEmits<{
  apply: [value: string]
}>()

const gender = ref('')
const age = ref('')
const pitch = ref('')
const style = ref('')
const accent = ref('')
const dialect = ref('')

const genders = [
  { value: '', label: 'Any gender' },
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]
const ages = [
  { value: '', label: 'Any age' },
  { value: 'child', label: 'Child' },
  { value: 'teenager', label: 'Teenager' },
  { value: 'young adult', label: 'Young adult' },
  { value: 'middle-aged', label: 'Middle-aged' },
  { value: 'elderly', label: 'Elderly' },
]
const pitches = [
  { value: '', label: 'Any pitch' },
  { value: 'very low pitch', label: 'Very low' },
  { value: 'low pitch', label: 'Low' },
  { value: 'moderate pitch', label: 'Moderate' },
  { value: 'high pitch', label: 'High' },
  { value: 'very high pitch', label: 'Very high' },
]
const styles = [
  { value: '', label: 'Normal' },
  { value: 'whisper', label: 'Whisper' },
]
const accents = [
  { value: '', label: 'No English accent' },
  { value: 'american accent', label: 'American' },
  { value: 'british accent', label: 'British' },
  { value: 'australian accent', label: 'Australian' },
  { value: 'canadian accent', label: 'Canadian' },
  { value: 'indian accent', label: 'Indian' },
  { value: 'chinese accent', label: 'Chinese' },
  { value: 'korean accent', label: 'Korean' },
  { value: 'japanese accent', label: 'Japanese' },
  { value: 'portuguese accent', label: 'Portuguese' },
  { value: 'russian accent', label: 'Russian' },
]
const dialects = [
  { value: '', label: 'No Chinese dialect' },
  { value: '河南话', label: '河南话' },
  { value: '陕西话', label: '陕西话' },
  { value: '四川话', label: '四川话' },
  { value: '贵州话', label: '贵州话' },
  { value: '云南话', label: '云南话' },
  { value: '桂林话', label: '桂林话' },
  { value: '济南话', label: '济南话' },
  { value: '石家庄话', label: '石家庄话' },
  { value: '甘肃话', label: '甘肃话' },
  { value: '宁夏话', label: '宁夏话' },
  { value: '青岛话', label: '青岛话' },
  { value: '东北话', label: '东北话' },
]

const built = computed(() =>
  [gender.value, age.value, pitch.value, style.value, accent.value, dialect.value]
    .filter(Boolean)
    .join(', '),
)

function apply(): void {
  emit('apply', built.value)
}

function clear(): void {
  gender.value = ''
  age.value = ''
  pitch.value = ''
  style.value = ''
  accent.value = ''
  dialect.value = ''
  emit('apply', '')
}
</script>

<template>
  <div class="voice-designer">
    <div class="voice-designer-grid">
      <div class="field">
        <label class="field-label">Gender</label>
        <select v-model="gender" class="select">
          <option v-for="option in genders" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="field">
        <label class="field-label">Age</label>
        <select v-model="age" class="select">
          <option v-for="option in ages" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="field">
        <label class="field-label">Pitch</label>
        <select v-model="pitch" class="select">
          <option v-for="option in pitches" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="field">
        <label class="field-label">Style</label>
        <select v-model="style" class="select">
          <option v-for="option in styles" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="field">
        <label class="field-label">English accent</label>
        <select v-model="accent" class="select">
          <option v-for="option in accents" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="field">
        <label class="field-label">Chinese dialect</label>
        <select v-model="dialect" class="select">
          <option v-for="option in dialects" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
    </div>

    <div class="voice-designer-foot">
      <span class="field-hint">
        {{ built || 'Choose attributes to build a description.' }}
      </span>
      <div class="row">
        <button type="button" class="btn btn-ghost btn-sm" @click="clear">
          Clear
        </button>
        <button type="button" class="btn btn-secondary btn-sm" @click="apply">
          Apply to description
        </button>
      </div>
    </div>
    <p class="field-hint" style="margin-top: 6px">
      English accents apply to English speech; Chinese dialects apply to Chinese
      speech. Voice design is most stable in English and Chinese.
    </p>
  </div>
</template>

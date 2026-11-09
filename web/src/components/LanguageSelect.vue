<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Check, ChevronDown, Search } from '@lucide/vue'
import type { Language } from '../lib/types'

const props = withDefaults(
  defineProps<{
    modelValue: string | null
    languages: Language[]
    placeholder?: string
    disabled?: boolean
  }>(),
  {
    placeholder: 'Auto-detect',
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const open = ref(false)
const query = ref('')
const root = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)

const selected = computed(
  () => props.languages.find((language) => language.id === props.modelValue) || null,
)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const list = needle
    ? props.languages.filter(
        (language) =>
          language.name.toLowerCase().includes(needle) ||
          language.id.toLowerCase().includes(needle),
      )
    : props.languages
  return list.slice(0, 120)
})

function toggle(): void {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    query.value = ''
    void nextTick(() => searchInput.value?.focus())
  }
}

function select(id: string | null): void {
  emit('update:modelValue', id)
  open.value = false
  query.value = ''
}

function onDocumentPointer(event: PointerEvent): void {
  if (root.value && !root.value.contains(event.target as Node)) {
    open.value = false
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    open.value = false
  }
}

watch(
  () => props.modelValue,
  () => {
    open.value = false
  },
)

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointer)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointer)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="language-select">
    <button
      type="button"
      class="language-button"
      :class="{ open }"
      :disabled="disabled"
      @click="toggle"
    >
      <span class="language-button-label" :class="{ placeholder: !selected }">
        {{ selected?.name || placeholder }}
      </span>
      <ChevronDown :size="15" />
    </button>

    <div v-if="open" class="language-menu">
      <div class="language-search-wrap">
        <Search :size="14" class="language-search-icon" />
        <input
          ref="searchInput"
          v-model="query"
          class="language-search"
          type="search"
          placeholder="Search 600+ languages…"
          @keydown.esc="open = false"
        />
      </div>
      <div class="language-list">
        <button
          type="button"
          class="language-option"
          :class="{ active: !modelValue }"
          @click="select(null)"
        >
          <span>Auto-detect</span>
          <span class="lang-id">auto</span>
        </button>
        <button
          v-for="language in filtered"
          :key="language.id"
          type="button"
          class="language-option"
          :class="{ active: language.id === modelValue }"
          @click="select(language.id)"
        >
          <span>{{ language.name }}</span>
          <span class="row" style="gap: 6px">
            <Check v-if="language.id === modelValue" :size="12" />
            <span class="lang-id">{{ language.id }}</span>
          </span>
        </button>
        <div v-if="!filtered.length" class="language-empty">
          No languages found. Try a different spelling.
        </div>
      </div>
    </div>
  </div>
</template>

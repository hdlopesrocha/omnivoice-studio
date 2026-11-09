<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Download,
  History as HistoryIcon,
  Mic2,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Wand2,
} from '@lucide/vue'
import ResultCard from '../components/ResultCard.vue'
import { api, getErrorMessage } from '../lib/api'
import {
  formatDate,
  formatTime,
  languageName,
  truncate,
} from '../lib/format'
import { refreshHistory, store } from '../lib/store'
import { toast } from '../lib/toast'
import type { OutputMeta, TTSMode } from '../lib/types'

const selectedId = ref<string | null>(null)
const filter = ref<'all' | TTSMode>('all')
const search = ref('')

const filterOptions: { value: 'all' | TTSMode; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'voice', label: 'My voices' },
  { value: 'design', label: 'Designed' },
  { value: 'auto', label: 'Auto' },
]

const filtered = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return store.history.filter((item) => {
    if (filter.value !== 'all' && item.mode !== filter.value) return false
    if (!needle) return true
    return (
      item.text_preview.toLowerCase().includes(needle) ||
      (item.voice_name || '').toLowerCase().includes(needle) ||
      (item.instruct || '').toLowerCase().includes(needle)
    )
  })
})

const selected = computed(
  () => store.history.find((item) => item.id === selectedId.value) || null,
)

watch(
  () => store.history,
  (history) => {
    if (!history.length) {
      selectedId.value = null
      return
    }
    if (!selectedId.value || !history.some((item) => item.id === selectedId.value)) {
      selectedId.value = history[0]?.id || null
    }
  },
  { immediate: true },
)

watch(filtered, (items) => {
  if (!items.some((item) => item.id === selectedId.value)) {
    selectedId.value = items[0]?.id || null
  }
})

function modeIcon(mode: TTSMode) {
  if (mode === 'design') return Wand2
  if (mode === 'auto') return Sparkles
  return Mic2
}

function modeLabel(item: OutputMeta): string {
  if (item.mode === 'design') return 'Designed voice'
  if (item.mode === 'auto') return 'Auto voice'
  return item.voice_name || 'Trained voice'
}

async function refresh(): Promise<void> {
  await refreshHistory()
  toast('info', 'History refreshed', `${store.history.length} generations loaded.`)
}

async function remove(item: OutputMeta): Promise<void> {
  if (!window.confirm('Delete this generation? The audio file will be removed.')) {
    return
  }
  try {
    await api.deleteOutput(item.id)
    await refreshHistory()
    toast('success', 'Generation deleted')
  } catch (error) {
    toast('error', 'Delete failed', getErrorMessage(error))
  }
}

onMounted(() => {
  void refreshHistory()
})
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">History.</h1>
        <p class="page-subtitle">
          Every generation is written to the local data volume. Play, download,
          or clean up old files here.
        </p>
      </div>
      <button type="button" class="btn btn-secondary" @click="refresh">
        <RefreshCw :size="14" />
        Refresh
      </button>
    </div>

    <div class="history-layout">
      <section class="stack">
        <div class="card card-pad" style="padding: 14px">
          <div class="row-between" style="flex-wrap: wrap">
            <div class="segmented">
              <button
                v-for="option in filterOptions"
                :key="option.value"
                type="button"
                class="segment"
                :class="{ active: filter === option.value }"
                @click="filter = option.value"
              >
                {{ option.label }}
              </button>
            </div>
            <div style="position: relative; min-width: 180px; flex: 1; max-width: 280px">
              <Search
                :size="14"
                style="position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: var(--muted-2)"
              />
              <input
                v-model="search"
                class="input"
                style="padding-left: 32px"
                placeholder="Search history…"
              />
            </div>
          </div>
        </div>

        <div v-if="filtered.length" class="history-list">
          <div
            v-for="item in filtered"
            :key="item.id"
            class="history-row"
            :class="{ active: selectedId === item.id }"
            role="button"
            tabindex="0"
            @click="selectedId = item.id"
            @keydown.enter.prevent="selectedId = item.id"
            @keydown.space.prevent="selectedId = item.id"
          >
            <span class="history-icon">
              <component :is="modeIcon(item.mode)" :size="16" />
            </span>
            <span class="history-main">
              <span class="history-title">{{ truncate(item.text_preview, 130) }}</span>
              <span class="history-meta">
                <span>{{ modeLabel(item) }}</span>
                <span>{{ formatTime(item.duration_seconds) }}</span>
                <span>{{ item.format.toUpperCase() }}</span>
                <span>{{ formatDate(item.created_at) }}</span>
              </span>
            </span>
            <span class="history-actions" @click.stop>
              <a
                :href="api.outputUrl(item.id, true)"
                class="icon-btn"
                title="Download"
                download
              >
                <Download :size="15" />
              </a>
              <button
                type="button"
                class="icon-btn danger"
                title="Delete"
                @click="remove(item)"
              >
                <Trash2 :size="15" />
              </button>
            </span>
          </div>
        </div>

        <div v-else class="card card-pad">
          <div class="empty-state" style="min-height: 280px">
            <div class="empty-visual" style="width: 58px; height: 58px">
              <HistoryIcon :size="23" class="muted" />
            </div>
            <div class="empty-title">
              {{ store.history.length ? 'No matching generations' : 'No generations yet' }}
            </div>
            <div class="empty-text">
              {{
                store.history.length
                  ? 'Try a different filter or search term.'
                  : 'Generate speech in the Studio or Design view and it will show up here.'
              }}
            </div>
          </div>
        </div>
      </section>

      <aside v-if="selected" class="card history-detail">
        <div class="card-head">
          <div>
            <div class="card-title">Selected generation</div>
            <div class="card-sub">{{ formatDate(selected.created_at) }}</div>
          </div>
          <span class="badge">{{ selected.format.toUpperCase() }}</span>
        </div>

        <div class="history-detail-text">{{ selected.text || selected.text_preview }}</div>

        <div class="result-shell" style="margin-top: 14px">
          <ResultCard
            :src="api.outputUrl(selected.id)"
            :output-id="selected.id"
            :duration="selected.duration_seconds"
            :rtf="selected.rtf"
            :format="selected.format"
            :voice-label="modeLabel(selected)"
            :language-label="
              selected.language_variant || selected.language
                ? languageName(
                    selected.language_variant || selected.language,
                    store.languages,
                  )
                : 'Auto-detect'
            "
            title="Audio"
            subtitle="Play the file or download the original."
          />
        </div>
      </aside>
    </div>
  </div>
</template>

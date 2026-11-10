<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  AlertTriangle,
  AudioLines,
  ExternalLink,
  History,
  Info,
  Layers3,
  ListTodo,
  Mic2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  WifiOff,
} from '@lucide/vue'
import ToastStack from './components/ToastStack.vue'
import { api, getErrorMessage } from './lib/api'
import {
  activeJobCount,
  bootstrap,
  refreshHealth,
  startHealthPolling,
  startJobPolling,
  stopHealthPolling,
  stopJobPolling,
  store,
} from './lib/store'
import { toast } from './lib/toast'

const route = useRoute()

const navItems = [
  { to: '/', label: 'Studio', icon: AudioLines },
  { to: '/voices', label: 'Voices', icon: Mic2 },
  { to: '/design', label: 'Design', icon: Sparkles },
  { to: '/batch', label: 'Batch', icon: Layers3 },
  { to: '/jobs', label: 'Jobs', icon: ListTodo },
  { to: '/history', label: 'History', icon: History },
  { to: '/about', label: 'About', icon: Info },
]

const pageTitle = computed(() => String(route.meta.title || 'Studio'))
const pageSubtitle = computed(() => String(route.meta.subtitle || ''))
const health = computed(() => store.health)

const statusClass = computed(() => {
  if (!store.online) return 'error'
  if (!health.value) return 'loading'
  if (health.value.status === 'ok') return 'ok'
  if (health.value.status === 'error') return 'error'
  return 'loading'
})

const statusLabel = computed(() => {
  if (!store.online) return 'Offline'
  if (!health.value) return 'Connecting'
  if (health.value.status === 'ok') return 'Local · Ready'
  if (health.value.status === 'error') return 'Model error'
  return 'Warming up'
})

const statusTitle = computed(() => {
  if (!store.online) return store.lastError || 'The engine is not reachable.'
  if (!health.value) return 'Connecting to the engine…'
  return `${health.value.message} · ${health.value.device}`
})

const showLoadingBanner = computed(
  () => store.online && health.value?.status === 'loading',
)

const showErrorBanner = computed(
  () => store.online && health.value?.status === 'error',
)

const showOfflineBanner = computed(() => store.booted && !store.online)

const loadingDetail = computed(() => {
  const elapsed = health.value?.load_seconds
  const suffix = elapsed ? ` (${Math.round(elapsed)}s elapsed)` : ''
  return `First boot downloads the model weights. This can take a few minutes${suffix}. The UI will unlock automatically.`
})

async function retryModel(): Promise<void> {
  try {
    await api.reloadModel()
    toast('info', 'Reloading model', 'The engine is restarting the OmniVoice loader.')
    await refreshHealth()
  } catch (error) {
    toast('error', 'Could not reload the model', getErrorMessage(error))
  }
}

function openDocs(): void {
  window.open(api.docsUrl(), '_blank', 'noopener,noreferrer')
}

onMounted(async () => {
  await bootstrap()
  startHealthPolling()
  startJobPolling()
})

onBeforeUnmount(() => {
  stopHealthPolling()
  stopJobPolling()
})
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">
          <div class="brand-bars">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </div>
        <div>
          <div class="brand-name">OmniVoice</div>
          <div class="brand-sub">Studio</div>
        </div>
      </div>

      <nav class="nav" aria-label="Main navigation">
        <div class="nav-label">Workspace</div>
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          active-class="active"
          :exact-active-class="item.to === '/' ? 'active' : undefined"
          :aria-label="item.label"
          :title="item.label"
        >
          <span class="nav-icon"><component :is="item.icon" :size="18" /></span>
          <span class="nav-text">{{ item.label }}</span>
          <span
            v-if="item.to === '/jobs' && activeJobCount > 0"
            class="nav-badge"
          >
            {{ activeJobCount }}
          </span>
        </RouterLink>
      </nav>

      <div class="sidebar-foot">
        <div class="privacy-badge">
          <ShieldCheck :size="15" />
          <span>
            Local-first. Audio, voices, and history stay in your Docker volume.
          </span>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" @click="openDocs">
          <ExternalLink :size="13" />
          API documentation
        </button>
        <div class="sidebar-version">v{{ health?.version || '1.0.0' }} · OmniVoice</div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div>
          <div class="topbar-title">{{ pageTitle }}</div>
          <div class="topbar-subtitle">{{ pageSubtitle }}</div>
        </div>
        <div class="topbar-actions">
          <RouterLink
            v-if="activeJobCount > 0"
            to="/jobs"
            class="status-pill loading"
            :title="`${activeJobCount} active job(s)`"
          >
            <span class="status-dot" />
            {{ activeJobCount }} job{{ activeJobCount === 1 ? '' : 's' }}
          </RouterLink>
          <span class="status-pill" :class="statusClass" :title="statusTitle">
            <span class="status-dot" />
            {{ statusLabel }}
          </span>
          <button
            type="button"
            class="icon-btn"
            title="Open API docs"
            aria-label="Open API docs"
            @click="openDocs"
          >
            <ExternalLink :size="16" />
          </button>
        </div>
      </header>

      <div v-if="showLoadingBanner" class="banner loading">
        <div class="banner-icon">
          <span class="spinner accent" />
        </div>
        <div class="banner-body">
          <div class="banner-title">OmniVoice is warming up</div>
          <div class="banner-text">{{ loadingDetail }}</div>
        </div>
        <div class="banner-actions">
          <span class="badge">{{ health?.device }}</span>
        </div>
      </div>

      <div v-if="showErrorBanner" class="banner error">
        <div class="banner-icon">
          <AlertTriangle :size="18" />
        </div>
        <div class="banner-body">
          <div class="banner-title">The model failed to load</div>
          <div class="banner-text">
            {{ health?.error || 'Check the engine logs for details.' }}
          </div>
        </div>
        <div class="banner-actions">
          <button type="button" class="btn btn-secondary btn-sm" @click="retryModel">
            <RefreshCw :size="13" />
            Retry
          </button>
        </div>
      </div>

      <div v-if="showOfflineBanner" class="banner error offline">
        <div class="banner-icon">
          <WifiOff :size="18" />
        </div>
        <div class="banner-body">
          <div class="banner-title">Engine unreachable</div>
          <div class="banner-text">
            {{ store.lastError || 'Start the Docker stack and refresh this page.' }}
          </div>
        </div>
        <div class="banner-actions">
          <button type="button" class="btn btn-secondary btn-sm" @click="refreshHealth">
            <RefreshCw :size="13" />
            Reconnect
          </button>
        </div>
      </div>

      <main class="page">
        <RouterView v-slot="{ Component }">
          <Transition name="fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>

    <ToastStack />
  </div>
</template>

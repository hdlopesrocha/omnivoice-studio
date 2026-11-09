import { computed, reactive } from 'vue'
import { api, getErrorMessage } from './api'
import { PORTUGUESE_VARIANT_OPTIONS } from './language'
import type { Health, Job, Language, OutputMeta, Voice } from './types'

export const store = reactive({
  health: null as Health | null,
  voices: [] as Voice[],
  languages: [] as Language[],
  popularLanguages: [] as string[],
  history: [] as OutputMeta[],
  jobs: [] as Job[],
  online: false,
  booted: false,
  lastError: '',
  loading: {
    health: false,
    voices: false,
    languages: false,
    history: false,
    jobs: false,
  },
})

export const modelReady = computed(
  () => store.health?.status === 'ok' && store.health?.model_loaded === true,
)

export const modelLoading = computed(
  () => !store.health || store.health.status === 'loading',
)

export const modelError = computed(
  () => store.health?.status === 'error' || (!store.online && store.booted),
)

export const activeJobs = computed(() =>
  store.jobs.filter((job) =>
    ['queued', 'running', 'cancelling'].includes(job.status),
  ),
)

export const activeJobCount = computed(() => activeJobs.value.length)

export const jobCounts = computed(() => {
  const counts = { queued: 0, running: 0, cancelling: 0 }
  for (const job of store.jobs) {
    if (job.status === 'queued') counts.queued += 1
    else if (job.status === 'running') counts.running += 1
    else if (job.status === 'cancelling') counts.cancelling += 1
  }
  return counts
})

let lastStatus: string | null = null
let bootstrapPromise: Promise<void> | null = null
let pollTimer: number | null = null
let polling = false

export async function refreshHealth(): Promise<void> {
  if (store.loading.health) return
  store.loading.health = true
  try {
    const health = await api.health()
    store.health = health
    store.online = true
    store.lastError = ''
    const previous = lastStatus
    lastStatus = health.status
    if (health.status === 'ok' && previous !== 'ok') {
      void refreshVoices()
      void refreshLanguages()
      void refreshHistory()
    }
  } catch (error) {
    store.online = false
    store.lastError = getErrorMessage(error)
  } finally {
    store.loading.health = false
    store.booted = true
  }
}

export async function refreshVoices(): Promise<void> {
  if (store.loading.voices) return
  store.loading.voices = true
  try {
    store.voices = await api.voices()
  } catch (error) {
    store.lastError = getErrorMessage(error)
  } finally {
    store.loading.voices = false
  }
}

export async function refreshLanguages(): Promise<void> {
  if (store.loading.languages || store.languages.length) return
  store.loading.languages = true
  try {
    const payload = await api.languages()
    const existing = new Set(payload.languages.map((language) => language.id))
    const normalized = payload.languages.map((language) =>
      language.id === 'pt'
        ? { ...language, name: 'Portuguese (generic)' }
        : language,
    )
    const languages = [
      ...normalized,
      ...PORTUGUESE_VARIANT_OPTIONS.filter(
        (language) => !existing.has(language.id),
      ),
    ]
    const popular = new Set([
      ...payload.popular,
      'pt-PT',
      'pt-BR',
    ])
    store.popularLanguages = [...popular]
    store.languages = languages.sort((a, b) => {
      const aPopular = popular.has(a.id) ? 1 : 0
      const bPopular = popular.has(b.id) ? 1 : 0
      if (aPopular !== bPopular) return bPopular - aPopular
      return a.name.localeCompare(b.name)
    })
  } catch (error) {
    store.lastError = getErrorMessage(error)
  } finally {
    store.loading.languages = false
  }
}

export async function refreshHistory(): Promise<void> {
  if (store.loading.history) return
  store.loading.history = true
  try {
    store.history = await api.history(100)
  } catch (error) {
    store.lastError = getErrorMessage(error)
  } finally {
    store.loading.history = false
  }
}

export function upsertJob(job: Job): void {
  const index = store.jobs.findIndex((item) => item.id === job.id)
  if (index >= 0) {
    store.jobs[index] = job
  } else {
    store.jobs.unshift(job)
  }
}

export async function refreshJobs(): Promise<void> {
  if (store.loading.jobs) return
  store.loading.jobs = true
  const previous = new Map(
    store.jobs.map((job) => [job.id, job.status] as const),
  )
  try {
    const payload = await api.jobs(100)
    store.jobs = payload.jobs
    for (const job of payload.jobs) {
      const prior = previous.get(job.id)
      if (job.status === 'completed' && prior !== 'completed') {
        if (job.type === 'tts') {
          void refreshHistory()
        } else {
          void refreshVoices()
        }
      }
    }
  } catch (error) {
    store.lastError = getErrorMessage(error)
  } finally {
    store.loading.jobs = false
  }
}

export async function cancelJob(jobId: string): Promise<Job> {
  const job = await api.cancelJob(jobId)
  upsertJob(job)
  return job
}

export async function cancelQueuedJobs(): Promise<number> {
  const result = await api.cancelQueuedJobs()
  await refreshJobs()
  return result.cancelled
}

export async function deleteJob(jobId: string): Promise<void> {
  await api.deleteJob(jobId)
  store.jobs = store.jobs.filter((job) => job.id !== jobId)
}

export function bootstrap(): Promise<void> {
  if (bootstrapPromise) return bootstrapPromise
  bootstrapPromise = (async () => {
    await Promise.allSettled([
      refreshHealth(),
      refreshVoices(),
      refreshLanguages(),
      refreshHistory(),
      refreshJobs(),
    ])
    store.booted = true
  })()
  return bootstrapPromise
}

export function startHealthPolling(): void {
  if (polling) return
  polling = true
  const tick = async () => {
    await refreshHealth()
    const delay =
      store.health?.status === 'loading' ? 3000 : store.online ? 15000 : 5000
    if (polling) {
      pollTimer = window.setTimeout(tick, delay)
    }
  }
  void tick()
}

export function stopHealthPolling(): void {
  polling = false
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

let jobPollTimer: number | null = null
let jobPolling = false

export function startJobPolling(): void {
  if (jobPolling) return
  jobPolling = true
  const tick = async () => {
    await refreshJobs()
    const delay = activeJobCount.value > 0 ? 1500 : 8000
    if (jobPolling) {
      jobPollTimer = window.setTimeout(tick, delay)
    }
  }
  void tick()
}

export function stopJobPolling(): void {
  jobPolling = false
  if (jobPollTimer !== null) {
    window.clearTimeout(jobPollTimer)
    jobPollTimer = null
  }
}

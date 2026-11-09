import type {
  AudioFormat,
  Health,
  Info,
  Job,
  JobsResponse,
  LanguagesResponse,
  OutputMeta,
  SampleUpload,
  TTSRequest,
  TTSResult,
  Voice,
  VoiceCreatePayload,
  VoiceRetrainPayload,
} from './types'

const rawBase = import.meta.env.VITE_API_BASE_URL || '/api'
export const API_BASE = rawBase.replace(/\/+$/, '')

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

async function errorFrom(response: Response): Promise<ApiError> {
  let detail = response.statusText || `Request failed (${response.status})`
  try {
    const payload = await response.json()
    const raw = payload?.detail
    if (typeof raw === 'string') {
      detail = raw
    } else if (Array.isArray(raw)) {
      detail = raw
        .map((item: { msg?: string }) => item?.msg || JSON.stringify(item))
        .join('; ')
    } else if (raw) {
      detail = JSON.stringify(raw)
    }
  } catch {
    // Keep the status text when the response is not JSON.
  }
  return new ApiError(response.status, detail)
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init)
  if (!response.ok) {
    throw await errorFrom(response)
  }
  return (await response.json()) as T
}

function numberHeader(response: Response, name: string): number {
  const value = Number(response.headers.get(name) || 0)
  return Number.isFinite(value) ? value : 0
}

export const api = {
  health(): Promise<Health> {
    return requestJson<Health>('/health')
  },

  info(): Promise<Info> {
    return requestJson<Info>('/info')
  },

  languages(): Promise<LanguagesResponse> {
    return requestJson<LanguagesResponse>('/languages')
  },

  reloadModel(): Promise<{ status: string }> {
    return requestJson<{ status: string }>('/model/reload', { method: 'POST' })
  },

  async voices(): Promise<Voice[]> {
    const payload = await requestJson<{ voices: Voice[] }>('/voices')
    return payload.voices
  },

  async createVoice(payload: VoiceCreatePayload): Promise<Voice> {
    const form = new FormData()
    form.append('name', payload.name)
    form.append('transcript', payload.transcript)
    form.append('language', payload.language || '')
    form.append('consent', 'true')
    form.append('audio', payload.audio, payload.filename)
    return requestJson<Voice>('/voices', { method: 'POST', body: form })
  },

  async retrainVoice(voiceId: string, payload: VoiceRetrainPayload): Promise<Voice> {
    const form = new FormData()
    if (payload.name !== undefined) form.append('name', payload.name || '')
    if (payload.transcript !== undefined) form.append('transcript', payload.transcript || '')
    if (payload.language !== undefined) form.append('language', payload.language || '')
    form.append('consent', 'true')
    if (payload.audio) form.append('audio', payload.audio, payload.filename || 'sample.wav')
    return requestJson<Voice>(`/voices/${voiceId}/retrain`, {
      method: 'POST',
      body: form,
    })
  },

  renameVoice(voiceId: string, name: string): Promise<Voice> {
    return requestJson<Voice>(`/voices/${voiceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
  },

  deleteVoice(voiceId: string): Promise<{ ok: boolean }> {
    return requestJson<{ ok: boolean }>(`/voices/${voiceId}`, { method: 'DELETE' })
  },

  jobs(limit = 100): Promise<JobsResponse> {
    return requestJson<JobsResponse>(`/jobs?limit=${limit}`)
  },

  job(jobId: string): Promise<Job> {
    return requestJson<Job>(`/jobs/${jobId}`)
  },

  submitTtsJob(payload: TTSRequest): Promise<Job> {
    return requestJson<Job>('/jobs/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },

  async submitVoiceJob(payload: VoiceCreatePayload): Promise<Job> {
    const form = new FormData()
    form.append('name', payload.name)
    form.append('transcript', payload.transcript)
    form.append('language', payload.language || '')
    form.append('consent', 'true')
    form.append('audio', payload.audio, payload.filename)
    return requestJson<Job>('/jobs/voices', { method: 'POST', body: form })
  },

  async submitRetrainJob(
    voiceId: string,
    payload: VoiceRetrainPayload,
  ): Promise<Job> {
    const form = new FormData()
    if (payload.name !== undefined) form.append('name', payload.name || '')
    if (payload.transcript !== undefined) {
      form.append('transcript', payload.transcript || '')
    }
    if (payload.language !== undefined) {
      form.append('language', payload.language || '')
    }
    form.append('consent', 'true')
    if (payload.audio) {
      form.append('audio', payload.audio, payload.filename || 'sample.wav')
    }
    return requestJson<Job>(`/jobs/voices/${voiceId}/retrain`, {
      method: 'POST',
      body: form,
    })
  },

  submitPreviewJob(voiceId: string, text?: string): Promise<Job> {
    const query = text ? `?text=${encodeURIComponent(text)}` : ''
    return requestJson<Job>(`/jobs/voices/${voiceId}/preview${query}`, {
      method: 'POST',
    })
  },

  cancelJob(jobId: string): Promise<Job> {
    return requestJson<Job>(`/jobs/${jobId}/cancel`, { method: 'POST' })
  },

  cancelQueuedJobs(): Promise<{ cancelled: number }> {
    return requestJson<{ cancelled: number }>('/jobs/cancel-queued', {
      method: 'POST',
    })
  },

  deleteJob(jobId: string): Promise<{ ok: boolean }> {
    return requestJson<{ ok: boolean }>(`/jobs/${jobId}`, {
      method: 'DELETE',
    })
  },

  jobAudioUrl(jobId: string, download = false): string {
    return apiUrl(`/jobs/${jobId}/audio${download ? '?download=1' : ''}`)
  },

  async previewVoice(voiceId: string, text?: string): Promise<Blob> {
    const query = text ? `?text=${encodeURIComponent(text)}` : ''
    const response = await fetch(apiUrl(`/voices/${voiceId}/preview${query}`), {
      method: 'POST',
    })
    if (!response.ok) throw await errorFrom(response)
    return response.blob()
  },

  async tts(payload: TTSRequest): Promise<TTSResult> {
    const response = await fetch(apiUrl('/tts'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw await errorFrom(response)
    const blob = await response.blob()
    return {
      blob,
      outputId: response.headers.get('X-Output-Id') || '',
      duration: numberHeader(response, 'X-Audio-Duration'),
      generationSeconds: numberHeader(response, 'X-Generation-Seconds'),
      rtf: response.headers.get('X-RTF')
        ? numberHeader(response, 'X-RTF')
        : null,
      format: (payload.response_format || 'wav') as AudioFormat,
    }
  },

  async history(limit = 100): Promise<OutputMeta[]> {
    const payload = await requestJson<{ outputs: OutputMeta[] }>(
      `/outputs?limit=${limit}`,
    )
    return payload.outputs
  },

  deleteOutput(outputId: string): Promise<{ ok: boolean }> {
    return requestJson<{ ok: boolean }>(`/outputs/${outputId}`, { method: 'DELETE' })
  },

  outputUrl(outputId: string, download = false): string {
    return apiUrl(`/outputs/${outputId}${download ? '?download=1' : ''}`)
  },

  referenceUrl(voiceId: string): string {
    return apiUrl(`/voices/${voiceId}/reference`)
  },

  previewUrl(voiceId: string, version?: string | null): string {
    const suffix = version ? `?v=${encodeURIComponent(version)}` : ''
    return apiUrl(`/voices/${voiceId}/preview${suffix}`)
  },

  docsUrl(): string {
    return apiUrl('/docs')
  },
}

export function toSampleUpload(file: File): SampleUpload {
  return { blob: file, filename: file.name }
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'Something went wrong'
}

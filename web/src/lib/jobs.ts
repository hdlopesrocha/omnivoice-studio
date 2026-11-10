import { api } from './api'
import { upsertJob } from './store'
import type { Job } from './types'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'cancelling'])

export function isJobActive(job: Job | null | undefined): boolean {
  return Boolean(job && ACTIVE_STATUSES.has(job.status))
}

export function jobTitle(job: Job): string {
  const summary = job.summary
  if (job.type === 'tts') {
    return summary.text_preview || 'Speech generation'
  }
  if (job.type === 'tts_batch') {
    return `Batch · ${summary.count || 'multiple'} item(s)`
  }
  if (job.type === 'transcribe') {
    return `Transcribe ${summary.filename || 'audio'}`
  }
  if (job.type === 'voice_train') {
    return `Train ${summary.name || 'voice'}`
  }
  if (job.type === 'voice_retrain') {
    return `Retrain ${summary.name || 'voice'}`
  }
  if (job.type === 'voice_preview') {
    return `Preview ${summary.voice_name || 'voice'}`
  }
  return job.type
}

export function jobTypeLabel(job: Job): string {
  if (job.type === 'tts') return 'Speech'
  if (job.type === 'tts_batch') return 'Batch speech'
  if (job.type === 'transcribe') return 'Transcription'
  if (job.type === 'voice_train') return 'Voice training'
  if (job.type === 'voice_retrain') return 'Voice retraining'
  if (job.type === 'voice_preview') return 'Voice preview'
  return job.type
}

export function jobStatusLabel(job: Job): string {
  if (job.status === 'queued') {
    return job.queue_position ? `Queued · #${job.queue_position}` : 'Queued'
  }
  if (job.status === 'running') return 'Running'
  if (job.status === 'cancelling') return 'Cancelling'
  if (job.status === 'completed') return 'Completed'
  if (job.status === 'failed') return 'Failed'
  if (job.status === 'cancelled') return 'Cancelled'
  return job.status
}

export function jobStatusClass(job: Job): string {
  if (job.status === 'completed') return 'ok'
  if (job.status === 'failed') return 'error'
  if (job.status === 'cancelled') return 'cancelled'
  if (job.status === 'cancelling') return 'warning'
  if (job.status === 'running') return 'running'
  return 'queued'
}

export function jobAudioUrl(job: Job, download = false): string {
  return api.jobAudioUrl(job.id, download)
}

export async function waitForJob(
  jobId: string,
  onUpdate?: (job: Job) => void,
  shouldStop?: () => boolean,
): Promise<Job> {
  while (true) {
    const job = await api.job(jobId)
    upsertJob(job)
    onUpdate?.(job)
    if (!isJobActive(job)) return job
    if (shouldStop?.()) return job
    await new Promise((resolve) => window.setTimeout(resolve, 800))
  }
}

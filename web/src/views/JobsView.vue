<script setup lang="ts">
import { computed, onMounted } from 'vue'
import {
  AudioLines,
  Ban,
  CheckCircle2,
  Clock3,
  Download,
  Mic2,
  RefreshCw,
  Trash2,
  Wand2,
  XCircle,
} from '@lucide/vue'
import AudioButton from '../components/AudioButton.vue'
import { formatDate, formatTime } from '../lib/format'
import {
  jobAudioUrl,
  jobStatusClass,
  jobStatusLabel,
  jobTitle,
  jobTypeLabel,
} from '../lib/jobs'
import {
  activeJobs,
  cancelJob,
  cancelQueuedJobs,
  deleteJob,
  jobCounts,
  refreshJobs,
  store,
} from '../lib/store'
import { toast } from '../lib/toast'
import type { Job } from '../lib/types'

const finishedJobs = computed(() =>
  store.jobs.filter(
    (job) => !['queued', 'running', 'cancelling'].includes(job.status),
  ),
)

function jobIcon(job: Job) {
  if (job.type === 'tts') return AudioLines
  if (job.type === 'voice_preview') return Wand2
  return Mic2
}

function voiceLink(job: Job): string {
  const voiceId =
    job.result?.voice_id || job.result?.id || job.summary.voice_id
  return voiceId ? `/voices?voice=${voiceId}` : '/voices'
}

function jobSubtitle(job: Job): string {
  const parts = [jobTypeLabel(job)]
  const language = job.summary.language_variant || job.summary.language
  if (language) parts.push(String(language))
  if (job.summary.format) parts.push(String(job.summary.format).toUpperCase())
  return parts.join(' · ')
}

async function cancel(job: Job): Promise<void> {
  try {
    const updated = await cancelJob(job.id)
    if (updated.status === 'cancelled') {
      toast('info', 'Job cancelled', 'The queued job was removed.')
    } else {
      toast(
        'info',
        'Cancellation requested',
        'The worker will stop after the current segment or step.',
      )
    }
  } catch (error) {
    toast(
      'error',
      'Could not cancel job',
      error instanceof Error ? error.message : 'Unknown error',
    )
  }
}

async function cancelAll(): Promise<void> {
  if (!jobCounts.value.queued) return
  if (!window.confirm('Cancel every queued job?')) return
  try {
    const count = await cancelQueuedJobs()
    toast('success', 'Queued jobs cancelled', `${count} job(s) removed.`)
  } catch (error) {
    toast(
      'error',
      'Could not cancel queued jobs',
      error instanceof Error ? error.message : 'Unknown error',
    )
  }
}

async function remove(job: Job): Promise<void> {
  if (!window.confirm('Delete this job record? Generated audio stays in History.')) {
    return
  }
  try {
    await deleteJob(job.id)
    toast('success', 'Job removed')
  } catch (error) {
    toast(
      'error',
      'Could not remove job',
      error instanceof Error ? error.message : 'Unknown error',
    )
  }
}

onMounted(() => {
  void refreshJobs()
})
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Jobs.</h1>
        <p class="page-subtitle">
          Everything model-bound goes through one local FIFO queue. Cancel
          queued jobs instantly; running jobs stop at the next safe checkpoint.
        </p>
      </div>
      <div class="row">
        <button type="button" class="btn btn-secondary" @click="refreshJobs">
          <RefreshCw :size="14" />
          Refresh
        </button>
        <button
          type="button"
          class="btn btn-danger"
          :disabled="!jobCounts.queued"
          @click="cancelAll"
        >
          <Ban :size="14" />
          Cancel queued ({{ jobCounts.queued }})
        </button>
      </div>
    </div>

    <div class="job-stats">
      <div class="job-stat">
        <div class="job-stat-label">Queued</div>
        <div class="job-stat-value">{{ jobCounts.queued }}</div>
      </div>
      <div class="job-stat">
        <div class="job-stat-label">Running</div>
        <div class="job-stat-value">{{ jobCounts.running }}</div>
      </div>
      <div class="job-stat">
        <div class="job-stat-label">Cancelling</div>
        <div class="job-stat-value">{{ jobCounts.cancelling }}</div>
      </div>
      <div class="job-stat">
        <div class="job-stat-label">Completed</div>
        <div class="job-stat-value">
          {{ store.jobs.filter((job) => job.status === 'completed').length }}
        </div>
      </div>
    </div>

    <section v-if="activeJobs.length" class="stack" style="margin-bottom: 24px">
      <div class="card-head" style="margin-bottom: 0">
        <div>
          <div class="card-title">Active queue</div>
          <div class="card-sub">One job runs at a time; the rest wait in order.</div>
        </div>
        <span class="badge accent">{{ activeJobs.length }} active</span>
      </div>

      <div class="job-list">
        <article v-for="job in activeJobs" :key="job.id" class="card job-card">
          <div class="job-head">
            <div class="job-icon">
              <component :is="jobIcon(job)" :size="18" />
            </div>
            <div class="job-main">
              <div class="job-title">{{ jobTitle(job) }}</div>
              <div class="job-sub">{{ jobSubtitle(job) }}</div>
            </div>
            <span class="job-status" :class="jobStatusClass(job)">
              <Clock3 v-if="job.status === 'queued'" :size="11" />
              <XCircle v-else-if="job.status === 'cancelling'" :size="11" />
              <span v-else class="spinner" style="width: 11px; height: 11px" />
              {{ jobStatusLabel(job) }}
            </span>
          </div>

          <div class="progress-track">
            <div
              class="progress-fill"
              :class="{ queued: job.status === 'queued' }"
              :style="{
                width:
                  job.status === 'queued'
                    ? '16%'
                    : `${Math.max(4, Math.round(job.progress * 100))}%`,
              }"
            />
          </div>

          <div class="job-meta">
            <span>{{ job.message }}</span>
            <span v-if="job.queue_position">Position #{{ job.queue_position }}</span>
            <span v-if="job.started_at">{{ job.elapsed_seconds.toFixed(0) }}s elapsed</span>
            <span>{{ formatDate(job.created_at) }}</span>
          </div>

          <div class="job-actions">
            <button
              v-if="job.can_cancel"
              type="button"
              class="btn btn-danger btn-sm"
              @click="cancel(job)"
            >
              <Ban :size="13" />
              Cancel
            </button>
            <span v-else-if="job.status === 'cancelling'" class="muted" style="font-size: 12px">
              Waiting for the current segment to finish…
            </span>
          </div>
        </article>
      </div>
    </section>

    <section class="stack">
      <div class="card-head" style="margin-bottom: 0">
        <div>
          <div class="card-title">Recent jobs</div>
          <div class="card-sub">Completed, failed, and cancelled jobs from this engine session.</div>
        </div>
      </div>

      <div v-if="finishedJobs.length" class="job-list">
        <article v-for="job in finishedJobs" :key="job.id" class="card job-card finished">
          <div class="job-head">
            <div class="job-icon">
              <component :is="jobIcon(job)" :size="18" />
            </div>
            <div class="job-main">
              <div class="job-title">{{ jobTitle(job) }}</div>
              <div class="job-sub">{{ jobSubtitle(job) }}</div>
            </div>
            <span class="job-status" :class="jobStatusClass(job)">
              <CheckCircle2 v-if="job.status === 'completed'" :size="11" />
              <XCircle v-else :size="11" />
              {{ jobStatusLabel(job) }}
            </span>
          </div>

          <div class="job-meta">
            <span
              v-if="
                job.result?.duration_seconds &&
                (job.type === 'tts' || job.type === 'voice_preview')
              "
            >
              {{ formatTime(job.result.duration_seconds) }} audio
            </span>
            <span
              v-else-if="job.result?.duration_seconds && job.type !== 'tts'"
            >
              reference {{ formatTime(job.result.duration_seconds) }}
            </span>
            <span v-if="job.elapsed_seconds">
              {{ job.elapsed_seconds.toFixed(0) }}s wall time
            </span>
            <span>{{ formatDate(job.created_at) }}</span>
            <span v-if="job.finished_at">finished {{ formatDate(job.finished_at) }}</span>
          </div>

          <div v-if="job.error" class="job-error">{{ job.error }}</div>

          <div class="job-actions">
            <template v-if="job.status === 'completed' && job.has_audio">
              <AudioButton :src="jobAudioUrl(job)" label="Play" />
              <a
                :href="jobAudioUrl(job, true)"
                class="btn btn-ghost btn-sm"
                download
              >
                <Download :size="13" />
                Download
              </a>
            </template>

            <RouterLink
              v-if="job.status === 'completed' && job.type !== 'tts'"
              :to="voiceLink(job)"
              class="btn btn-secondary btn-sm"
            >
              <Mic2 :size="13" />
              Open voice
            </RouterLink>

            <button
              type="button"
              class="icon-btn danger"
              title="Delete job record"
              @click="remove(job)"
            >
              <Trash2 :size="15" />
            </button>
          </div>
        </article>
      </div>

      <div v-else class="card card-pad">
        <div class="empty-state" style="min-height: 240px">
          <div class="empty-visual" style="width: 58px; height: 58px">
            <AudioLines :size="23" class="muted" />
          </div>
          <div class="empty-title">No jobs yet</div>
          <div class="empty-text">
            Generate speech, train a voice, or request a preview. Jobs will show
            up here with their queue position and progress.
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

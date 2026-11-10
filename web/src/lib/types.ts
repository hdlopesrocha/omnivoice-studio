export type TTSMode = 'voice' | 'design' | 'auto'
export type AudioFormat = 'wav' | 'mp3' | 'flac'

export interface Health {
  status: 'loading' | 'ok' | 'error'
  model_loaded: boolean
  device: string
  model_id: string
  asr_model: string
  asr_loaded: boolean
  message: string
  error: string | null
  uptime_seconds: number
  load_seconds: number | null
  sample_rate: number
  voices: number
  outputs: number
  jobs: number
  lora_adapter: string | null
  flashinfer: boolean
  version: string
}

export interface Info {
  name: string
  version: string
  model_id: string
  device: string
  sample_rate: number
  max_input_chars: number
  max_upload_mb: number
  min_voice_seconds: number
  max_voice_seconds: number
  max_queue_size: number
  max_job_history: number
  max_import_mb: number
  lora_adapter: string | null
  flashinfer: boolean
  normalize_text: boolean
  formats: AudioFormat[]
  modes: TTSMode[]
  preview_text: string
  languages: number
}

export interface Language {
  id: string
  name: string
  iso?: string | null
  hours?: number
  variant_of?: string | null
  requires_voice?: boolean
}

export interface LanguagesResponse {
  languages: Language[]
  popular: string[]
  count: number
}

export interface Voice {
  id: string
  name: string
  language: string | null
  transcript: string | null
  duration_seconds: number
  created_at: string
  updated_at: string
  has_preview: boolean
  preview_updated_at: string | null
}

export interface OutputMeta {
  id: string
  text: string
  text_preview: string
  mode: TTSMode
  voice_id: string | null
  voice_name: string | null
  instruct: string | null
  language: string | null
  language_variant?: string | null
  format: AudioFormat
  duration_seconds: number
  generation_seconds: number
  rtf: number | null
  seed?: number | null
  created_at: string
  size_bytes: number
}

export interface TTSRequest {
  text: string
  mode: TTSMode
  voice_id?: string | null
  instruct?: string | null
  style_instruct?: string | null
  language?: string | null
  language_variant?: string | null
  speed?: number | null
  duration?: number | null
  num_step?: number
  guidance_scale?: number
  denoise?: boolean
  t_shift?: number
  position_temperature?: number
  class_temperature?: number
  layer_penalty_factor?: number
  postprocess_output?: boolean
  pad_duration?: number
  fade_duration?: number
  audio_chunk_duration?: number
  audio_chunk_threshold?: number
  normalize_text?: boolean
  seed?: number | null
  response_format?: AudioFormat
}

export interface TTSResult {
  blob: Blob
  outputId: string
  duration: number
  generationSeconds: number
  rtf: number | null
  format: AudioFormat
}

export interface SampleUpload {
  blob: Blob
  filename: string
  seconds?: number
}

export interface VoiceCreatePayload {
  name: string
  transcript: string
  language: string | null
  audio: Blob
  filename: string
  preprocess_prompt?: boolean
}

export interface VoiceRetrainPayload {
  name?: string | null
  transcript?: string | null
  language?: string | null
  audio?: Blob | null
  filename?: string
  preprocess_prompt?: boolean
}

export type JobType =
  | 'tts'
  | 'tts_batch'
  | 'transcribe'
  | 'voice_train'
  | 'voice_retrain'
  | 'voice_preview'

export type JobStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface JobSummary {
  kind?: string
  text_preview?: string
  mode?: TTSMode
  voice_id?: string | null
  voice_name?: string | null
  language?: string | null
  language_variant?: string | null
  format?: AudioFormat
  name?: string
  transcript_provided?: boolean
  text?: string
  count?: number
  filename?: string
  style_instruct?: string | null
  seed?: number | null
  [key: string]: unknown
}

export interface JobResult {
  output_id?: string
  voice_id?: string
  voice_name?: string | null
  format?: AudioFormat
  duration_seconds?: number
  generation_seconds?: number
  rtf?: number | null
  preview_updated_at?: string | null
  items?: OutputMeta[]
  count?: number
  text?: string
  filename?: string
  id?: string
  name?: string
  language?: string | null
  transcript?: string | null
  created_at?: string
  updated_at?: string
  has_preview?: boolean
}

export interface Job {
  id: string
  type: JobType
  status: JobStatus
  progress: number
  message: string
  queue_position: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  elapsed_seconds: number
  summary: JobSummary
  result: JobResult | null
  error: string | null
  error_kind: string | null
  can_cancel: boolean
  has_audio: boolean
}

export interface JobsResponse {
  jobs: Job[]
  counts: {
    queued: number
    running: number
    cancelling: number
  }
  active: number
}

export interface BatchTTSRequest extends Omit<TTSRequest, 'text'> {
  texts: string[]
}

export interface TranscribeResult {
  text: string
  filename?: string
}

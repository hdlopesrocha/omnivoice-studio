import type { TTSRequest } from './types'

export interface AdvancedGeneration {
  style_instruct: string
  duration: number | null
  guidance_scale: number
  denoise: boolean
  t_shift: number
  position_temperature: number
  class_temperature: number
  layer_penalty_factor: number
  postprocess_output: boolean
  pad_duration: number
  fade_duration: number
  audio_chunk_duration: number
  audio_chunk_threshold: number
  normalize_text: boolean
  seed: number | null
}

export function defaultAdvanced(): AdvancedGeneration {
  return {
    style_instruct: '',
    duration: null,
    guidance_scale: 2,
    denoise: true,
    t_shift: 0.1,
    position_temperature: 5,
    class_temperature: 0,
    layer_penalty_factor: 5,
    postprocess_output: true,
    pad_duration: 0.1,
    fade_duration: 0.1,
    audio_chunk_duration: 15,
    audio_chunk_threshold: 30,
    normalize_text: false,
    seed: null,
  }
}

export function advancedToRequest(
  advanced: AdvancedGeneration,
): Partial<TTSRequest> {
  return {
    style_instruct: advanced.style_instruct.trim() || null,
    duration: advanced.duration,
    guidance_scale: advanced.guidance_scale,
    denoise: advanced.denoise,
    t_shift: advanced.t_shift,
    position_temperature: advanced.position_temperature,
    class_temperature: advanced.class_temperature,
    layer_penalty_factor: advanced.layer_penalty_factor,
    postprocess_output: advanced.postprocess_output,
    pad_duration: advanced.pad_duration,
    fade_duration: advanced.fade_duration,
    audio_chunk_duration: advanced.audio_chunk_duration,
    audio_chunk_threshold: advanced.audio_chunk_threshold,
    normalize_text: advanced.normalize_text,
    seed: advanced.seed,
  }
}

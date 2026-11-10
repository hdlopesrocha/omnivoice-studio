<script setup lang="ts">
import { defaultAdvanced, type AdvancedGeneration } from '../lib/generation'

const props = withDefaults(
  defineProps<{
    advanced: AdvancedGeneration
    showStyle?: boolean
  }>(),
  {
    showStyle: false,
  },
)

function onNullableNumber(event: Event, key: 'duration' | 'seed'): void {
  const raw = (event.target as HTMLInputElement).value.trim()
  if (!raw) {
    props.advanced[key] = null
    return
  }
  const value = Number(raw)
  if (Number.isFinite(value)) {
    props.advanced[key] = value
  }
}

function reset(): void {
  Object.assign(props.advanced, defaultAdvanced())
}
</script>

<template>
  <details class="advanced-panel">
    <summary>
      <span>Advanced generation controls</span>
      <span class="advanced-summary-hint">
        decoding, post-processing, long-form, seed
      </span>
    </summary>

    <div class="advanced-grid">
      <div v-if="showStyle" class="field field-full">
        <label class="field-label">Style hint (optional)</label>
        <input
          v-model="advanced.style_instruct"
          class="input"
          maxlength="300"
          placeholder="e.g. whisper, british accent"
        />
        <span class="field-hint">
          Combined with the reference voice. When the hint conflicts with the
          reference, the reference usually wins.
        </span>
      </div>

      <div class="field">
        <label class="field-label">Fixed duration</label>
        <input
          class="input"
          type="number"
          min="0.5"
          step="0.5"
          placeholder="auto"
          :value="advanced.duration ?? ''"
          @input="onNullableNumber($event, 'duration')"
        />
        <span class="field-hint">Seconds. Overrides speed when set.</span>
      </div>

      <div class="field">
        <label class="field-label">Seed</label>
        <input
          class="input"
          type="number"
          min="0"
          step="1"
          placeholder="random"
          :value="advanced.seed ?? ''"
          @input="onNullableNumber($event, 'seed')"
        />
        <span class="field-hint">Set a seed for reproducible sampling.</span>
      </div>

      <div class="field">
        <label class="field-label">Guidance scale</label>
        <input
          v-model.number="advanced.guidance_scale"
          class="input"
          type="number"
          min="0"
          max="20"
          step="0.1"
        />
        <span class="field-hint">Classifier-free guidance. Default 2.0.</span>
      </div>

      <div class="field">
        <label class="field-label">Time-step shift</label>
        <input
          v-model.number="advanced.t_shift"
          class="input"
          type="number"
          min="0"
          max="10"
          step="0.01"
        />
        <span class="field-hint">Lower values emphasise early steps.</span>
      </div>

      <div class="field">
        <label class="field-label">Position temperature</label>
        <input
          v-model.number="advanced.position_temperature"
          class="input"
          type="number"
          min="0"
          max="100"
          step="0.1"
        />
        <span class="field-hint">Mask-position sampling. 0 = greedy.</span>
      </div>

      <div class="field">
        <label class="field-label">Class temperature</label>
        <input
          v-model.number="advanced.class_temperature"
          class="input"
          type="number"
          min="0"
          max="10"
          step="0.05"
        />
        <span class="field-hint">Token sampling. 0 = deterministic.</span>
      </div>

      <div class="field">
        <label class="field-label">Layer penalty</label>
        <input
          v-model.number="advanced.layer_penalty_factor"
          class="input"
          type="number"
          min="0"
          max="100"
          step="0.5"
        />
        <span class="field-hint">Encourages lower codebook layers first.</span>
      </div>

      <div class="field">
        <label class="field-label">Pad duration</label>
        <input
          v-model.number="advanced.pad_duration"
          class="input"
          type="number"
          min="0"
          max="5"
          step="0.05"
        />
        <span class="field-hint">Silence added per side, in seconds.</span>
      </div>

      <div class="field">
        <label class="field-label">Fade duration</label>
        <input
          v-model.number="advanced.fade_duration"
          class="input"
          type="number"
          min="0"
          max="5"
          step="0.05"
        />
        <span class="field-hint">Fade-in/out curve, in seconds.</span>
      </div>

      <div class="field">
        <label class="field-label">Chunk duration</label>
        <input
          v-model.number="advanced.audio_chunk_duration"
          class="input"
          type="number"
          min="1"
          max="120"
          step="1"
        />
        <span class="field-hint">Target seconds per long-form chunk.</span>
      </div>

      <div class="field">
        <label class="field-label">Chunk threshold</label>
        <input
          v-model.number="advanced.audio_chunk_threshold"
          class="input"
          type="number"
          min="0"
          max="600"
          step="1"
        />
        <span class="field-hint">Estimated duration above which chunking starts.</span>
      </div>

      <div class="field field-full">
        <div class="advanced-checks">
          <label class="checkbox">
            <input v-model="advanced.denoise" type="checkbox" />
            <span>Denoise token</span>
          </label>
          <label class="checkbox">
            <input v-model="advanced.postprocess_output" type="checkbox" />
            <span>Post-process output (silence trim, fades, padding)</span>
          </label>
          <label class="checkbox">
            <input v-model="advanced.normalize_text" type="checkbox" />
            <span>Normalize numbers, dates, and currency</span>
          </label>
        </div>
        <span class="field-hint">
          Text normalization uses the engine's TN extras (included in this image).
        </span>
      </div>
    </div>

    <div class="row-between advanced-foot">
      <span class="field-hint">
        Defaults match OmniVoice's generation config.
      </span>
      <button type="button" class="btn btn-ghost btn-sm" @click="reset">
        Reset to defaults
      </button>
    </div>
  </details>
</template>

<script setup lang="ts">
import { AlertCircle, CheckCircle2, Info, X } from '@lucide/vue'
import { dismissToast, toasts } from '../lib/toast'
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast"
        :class="item.type"
      >
        <div class="toast-icon">
          <CheckCircle2 v-if="item.type === 'success'" :size="16" />
          <AlertCircle v-else-if="item.type === 'error'" :size="16" />
          <Info v-else :size="16" />
        </div>
        <div class="toast-main">
          <div class="toast-title">{{ item.title }}</div>
          <div v-if="item.message" class="toast-message">{{ item.message }}</div>
        </div>
        <button
          type="button"
          class="toast-close"
          aria-label="Dismiss notification"
          @click="dismissToast(item.id)"
        >
          <X :size="14" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

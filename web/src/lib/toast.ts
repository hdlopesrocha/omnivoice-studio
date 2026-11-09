import { reactive } from 'vue'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  type: ToastType
  title: string
  message?: string
}

export const toasts = reactive<ToastItem[]>([])

let nextId = 1

export function toast(
  type: ToastType,
  title: string,
  message?: string,
  duration = 5200,
): number {
  const id = nextId
  nextId += 1
  toasts.push({ id, type, title, message })
  if (duration > 0) {
    window.setTimeout(() => dismissToast(id), duration)
  }
  return id
}

export function dismissToast(id: number): void {
  const index = toasts.findIndex((item) => item.id === id)
  if (index >= 0) toasts.splice(index, 1)
}

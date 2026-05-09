import { createContext } from 'react'

export type ToastVariant = 'success' | 'error' | 'info' | 'warning'

export type ToastInput = {
  title?: string
  message: string
  variant?: ToastVariant
  duration?: number
}

export type ToastContextValue = {
  show: (toast: ToastInput) => number
  success: (message: string, title?: string) => number
  error: (message: string, title?: string) => number
  info: (message: string, title?: string) => number
  warning: (message: string, title?: string) => number
  dismiss: (id: number) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

export function getApiErrorMessage(error: unknown, fallback = '不明なエラーが発生しました'): string {
  if (error instanceof Error) return error.message || fallback
  if (typeof error === 'string') return error
  return fallback
}

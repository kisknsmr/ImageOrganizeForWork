import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  ToastContext,
  type ToastContextValue,
  type ToastInput,
  type ToastVariant,
} from './toastContext'

type ToastItem = Required<Omit<ToastInput, 'title'>> & {
  id: number
  title?: string
  leaving: boolean
}

const DEFAULT_DURATION = 3800
const LEAVE_DURATION = 220

function getVariantIcon(variant: ToastVariant): string {
  switch (variant) {
    case 'success':
      return '✓'
    case 'error':
      return '!'
    case 'warning':
      return '⚠'
    default:
      return 'i'
  }
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const idRef = useRef(0)
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)))
    const cleanupTimer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
      timersRef.current.delete(id)
    }, LEAVE_DURATION)
    timersRef.current.set(id, cleanupTimer)
  }, [])

  const show = useCallback(
    (toast: ToastInput) => {
      idRef.current += 1
      const id = idRef.current
      const item: ToastItem = {
        id,
        title: toast.title,
        message: toast.message,
        variant: toast.variant ?? 'info',
        duration: toast.duration ?? DEFAULT_DURATION,
        leaving: false,
      }
      setToasts((prev) => [...prev, item])
      const timer = setTimeout(() => dismiss(id), item.duration)
      timersRef.current.set(id, timer)
      return id
    },
    [dismiss],
  )

  useEffect(() => {
    const timers = timersRef.current
    return () => {
      timers.forEach((timer) => clearTimeout(timer))
      timers.clear()
    }
  }, [])

  const value = useMemo<ToastContextValue>(
    () => ({
      show,
      dismiss,
      success: (message, title) => show({ message, title, variant: 'success' }),
      error: (message, title) => show({ message, title, variant: 'error', duration: 5200 }),
      info: (message, title) => show({ message, title, variant: 'info' }),
      warning: (message, title) => show({ message, title, variant: 'warning' }),
    }),
    [show, dismiss],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" role="region" aria-live="polite" aria-label="Notifications">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast toast-${toast.variant} ${toast.leaving ? 'leaving' : ''}`}
            role={toast.variant === 'error' ? 'alert' : 'status'}
          >
            <div className={`toast-icon toast-icon-${toast.variant}`} aria-hidden="true">
              {getVariantIcon(toast.variant)}
            </div>
            <div className="toast-body">
              {toast.title && <p className="toast-title">{toast.title}</p>}
              <p className="toast-message">{toast.message}</p>
            </div>
            <button
              type="button"
              className="toast-close"
              onClick={() => dismiss(toast.id)}
              aria-label="閉じる"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

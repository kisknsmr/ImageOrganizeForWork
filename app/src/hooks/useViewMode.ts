import { useCallback, useEffect, useState } from 'react'

export type ViewMode = 'grid' | 'list'

const SIZE_MIN = 80
const SIZE_MAX = 280
const SIZE_DEFAULT = 140

type Stored = {
  mode: ViewMode
  size: number
}

function clampSize(value: number): number {
  if (Number.isNaN(value)) return SIZE_DEFAULT
  return Math.max(SIZE_MIN, Math.min(SIZE_MAX, Math.round(value)))
}

function load(key: string): Stored {
  if (typeof window === 'undefined') return { mode: 'grid', size: SIZE_DEFAULT }
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return { mode: 'grid', size: SIZE_DEFAULT }
    const parsed = JSON.parse(raw) as Partial<Stored>
    return {
      mode: parsed.mode === 'list' ? 'list' : 'grid',
      size: clampSize(Number(parsed.size ?? SIZE_DEFAULT)),
    }
  } catch {
    return { mode: 'grid', size: SIZE_DEFAULT }
  }
}

export function useViewMode(storageKey: string) {
  const fullKey = `photosortx.view.${storageKey}`
  const [state, setState] = useState<Stored>(() => load(fullKey))

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(fullKey, JSON.stringify(state))
    } catch {
      // ignore quota errors
    }
  }, [fullKey, state])

  const setMode = useCallback((mode: ViewMode) => {
    setState((prev) => (prev.mode === mode ? prev : { ...prev, mode }))
  }, [])

  const setSize = useCallback((size: number) => {
    const next = clampSize(size)
    setState((prev) => (prev.size === next ? prev : { ...prev, size: next }))
  }, [])

  return {
    mode: state.mode,
    size: state.size,
    setMode,
    setSize,
    sizeMin: SIZE_MIN,
    sizeMax: SIZE_MAX,
  } as const
}

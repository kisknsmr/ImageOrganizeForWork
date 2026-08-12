import { useCallback, useEffect, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from 'react'

const MIN_WIDTH = 240
const MAX_WIDTH = 760
/** キーボード操作 1 回あたりの変化量 */
const KEY_STEP = 16

function storageKeyFor(key: string): string {
  return `photosortx.pane.${key}`
}

function load(key: string): number | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(storageKeyFor(key))
    if (!raw) return null
    const value = Number(raw)
    return Number.isFinite(value) ? value : null
  } catch {
    return null
  }
}

function clamp(value: number, max: number): number {
  return Math.max(MIN_WIDTH, Math.min(max, Math.round(value)))
}

/**
 * 右サイドペインの幅を手動リサイズ可能にする。
 *
 * width が null の間は CSS 側の既定値（ビューポート幅に追従する clamp）が効く。
 * ドラッグして初めて明示的な px 幅になり、以降は localStorage に記憶する。
 * つまり「自動で合わせる」と「自分で決める」が両立する。
 *
 * 上限はウィンドウ幅の 60% にも制限する。狭いウィンドウで記憶した幅を
 * そのまま適用すると、一覧側が潰れて操作できなくなるため。
 */
export function useResizablePane(key: string) {
  // ref オブジェクトではなくコールバック ref で要素を受け取る
  // （レンダー中に ref を読まない形にするため）
  const [container, setContainer] = useState<HTMLDivElement | null>(null)
  const [width, setWidth] = useState<number | null>(() => load(key))
  const [isResizing, setIsResizing] = useState(false)

  const maxWidth = () =>
    typeof window === 'undefined' ? MAX_WIDTH : Math.min(MAX_WIDTH, window.innerWidth * 0.6)

  const persist = useCallback(
    (value: number | null) => {
      try {
        if (value == null) window.localStorage.removeItem(storageKeyFor(key))
        else window.localStorage.setItem(storageKeyFor(key), String(value))
      } catch {
        // 保存できなくても動作は続ける
      }
    },
    [key],
  )

  // ウィンドウが狭くなったとき、記憶した幅が広すぎるままにならないよう詰める
  useEffect(() => {
    const onResize = () => {
      setWidth((current) => (current == null ? null : clamp(current, maxWidth())))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    if (!container) return

    event.preventDefault()
    const handle = event.currentTarget
    handle.setPointerCapture(event.pointerId)
    setIsResizing(true)
    // ドラッグ中に文字が選択されるのを防ぐ
    document.body.style.userSelect = 'none'

    const move = (moveEvent: PointerEvent) => {
      const rect = container.getBoundingClientRect()
      setWidth(clamp(rect.right - moveEvent.clientX, maxWidth()))
    }

    const up = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', up)
      handle.removeEventListener('pointercancel', up)
      document.body.style.userSelect = ''
      setIsResizing(false)
      setWidth((current) => {
        persist(current)
        return current
      })
    }

    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', up)
    handle.addEventListener('pointercancel', up)
  }

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const fallback = container ? container.getBoundingClientRect().width * 0.28 : MIN_WIDTH
    const delta = event.key === 'ArrowLeft' ? KEY_STEP : -KEY_STEP
    setWidth((current) => {
      const next = clamp((current ?? fallback) + delta, maxWidth())
      persist(next)
      return next
    })
  }

  /** 既定（ビューポート追従）に戻す */
  const reset = () => {
    setWidth(null)
    persist(null)
  }

  return { setContainer, width, isResizing, onPointerDown, onKeyDown, reset }
}

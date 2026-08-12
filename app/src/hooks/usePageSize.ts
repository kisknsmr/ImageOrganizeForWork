import { useCallback, useState } from 'react'

/** 1 ページに表示する枚数の選択肢。サーバー側の上限は 500 なので 200 まで許容する */
export const PAGE_SIZE_OPTIONS = [40, 60, 80, 100, 150, 200] as const

const DEFAULT_PAGE_SIZE = 60

function storageKeyFor(key: string): string {
  return `photosortx.pageSize.${key}`
}

function load(key: string, fallback: number): number {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(storageKeyFor(key))
    const value = Number(raw)
    return PAGE_SIZE_OPTIONS.includes(value as (typeof PAGE_SIZE_OPTIONS)[number])
      ? value
      : fallback
  } catch {
    return fallback
  }
}

/**
 * 1 ページの表示枚数。ページごとに localStorage へ記憶する。
 *
 * 変更時はページ番号を 1 に戻す必要があるため、呼び出し側で onChange を受ける。
 */
export function usePageSize(key: string, fallback: number = DEFAULT_PAGE_SIZE) {
  const [pageSize, setPageSizeState] = useState<number>(() => load(key, fallback))

  const setPageSize = useCallback(
    (value: number) => {
      setPageSizeState(value)
      try {
        window.localStorage.setItem(storageKeyFor(key), String(value))
      } catch {
        // 保存できなくても動作は続ける
      }
    },
    [key],
  )

  return { pageSize, setPageSize }
}

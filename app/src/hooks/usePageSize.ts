import { useCallback, useState } from 'react'

/** 1 ページに表示する枚数の選択肢。サーバー側の上限は 500 なので 200 まで許容する */
export const PAGE_SIZE_OPTIONS = [40, 60, 80, 100, 150, 200] as const

/** 'auto' は画面に収まる枚数を自動で決める */
export type PageSizeSetting = number | 'auto'

const DEFAULT_SETTING: PageSizeSetting = 'auto'

function storageKeyFor(key: string): string {
  return `photosortx.pageSize.${key}`
}

function load(key: string, fallback: PageSizeSetting): PageSizeSetting {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(storageKeyFor(key))
    if (raw === 'auto') return 'auto'
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
 * 既定は 'auto'。広い画面で固定枚数だと、グリッドが数行で終わって
 * 下半分が余白になるため、画面に収まる枚数を既定にする。
 *
 * @param fitSize 'auto' のときに使う、画面に収まる件数
 */
export function usePageSize(key: string, fitSize: number, fallback: PageSizeSetting = DEFAULT_SETTING) {
  const [setting, setSettingState] = useState<PageSizeSetting>(() => load(key, fallback))

  const setSetting = useCallback(
    (value: PageSizeSetting) => {
      setSettingState(value)
      try {
        window.localStorage.setItem(storageKeyFor(key), String(value))
      } catch {
        // 保存できなくても動作は続ける
      }
    },
    [key],
  )

  return {
    /** 実際に使う件数 */
    pageSize: setting === 'auto' ? fitSize : setting,
    /** 選択されている設定（'auto' を含む） */
    setting,
    setPageSize: setSetting,
  }
}

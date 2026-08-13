import { useEffect, useState } from 'react'
import type { ViewMode } from './useViewMode'

/** サムネイル 1 マスの、画像以外に必要な高さ（内側余白 + ファイル名 + メタ行） */
const CELL_CHROME_H = 56
/** サムネイル 1 マスの、画像以外に必要な幅（内側余白） */
const CELL_CHROME_W = 16
/** グリッドの間隔（--sp-3） */
const GRID_GAP = 12
/** リスト表示の 1 行の高さ */
const LIST_ROW_H = 58
/** ヘッダー・ツールバー・操作カードが占める概算の高さ */
const CHROME_H = 260

function estimateGridWidth(sidePaneWidth: number): number {
  const viewport = window.innerWidth
  // ナビゲーションドロワー（狭い画面ではレールに変わる）
  const nav = viewport <= 1100 ? 80 : 264
  const pagePad = (viewport <= 720 ? 16 : 24) * 2
  const gap = 16
  return Math.max(240, viewport - nav - pagePad - sidePaneWidth - gap)
}

/**
 * 画面に収まる件数を見積もる。
 *
 * 広い画面ほど 1 ページの表示枚数を増やさないと、グリッドが数行で終わって
 * 下半分が余白になる。逆に狭い画面で大量に読むと待ち時間が増える。
 * 実測ではなく概算で決める（正確さより、余白が出ないことが目的）。
 */
export function useFitPageSize(mode: ViewMode, thumbSize: number, sidePaneWidth: number): number {
  const [fit, setFit] = useState(60)

  useEffect(() => {
    const compute = () => {
      const gridWidth = estimateGridWidth(sidePaneWidth)
      const usableHeight = Math.max(240, window.innerHeight - CHROME_H)

      if (mode === 'list') {
        setFit(Math.max(20, Math.ceil(usableHeight / LIST_ROW_H) + 4))
        return
      }

      const cellW = thumbSize + CELL_CHROME_W + GRID_GAP
      const cellH = thumbSize + CELL_CHROME_H + GRID_GAP
      const cols = Math.max(1, Math.floor((gridWidth + GRID_GAP) / cellW))
      // 1 行ぶん余分に読み、スクロールし始めた時点で下に続きがある状態にする
      const rows = Math.max(1, Math.ceil(usableHeight / cellH) + 1)
      setFit(Math.max(20, Math.min(500, cols * rows)))
    }

    compute()
    window.addEventListener('resize', compute)
    return () => window.removeEventListener('resize', compute)
  }, [mode, thumbSize, sidePaneWidth])

  return fit
}

import type { KeyboardEvent, PointerEvent } from 'react'

type PaneResizerProps = {
  onPointerDown: (event: PointerEvent<HTMLDivElement>) => void
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void
  onReset: () => void
  isResizing: boolean
}

/**
 * ペイン境界のリサイズハンドル。
 *
 * ドラッグで幅を変え、ダブルクリックで既定（ウィンドウ幅に追従）へ戻す。
 * キーボードでも操作できるよう role="separator" + 矢印キーに対応する。
 */
export function PaneResizer({ onPointerDown, onKeyDown, onReset, isResizing }: PaneResizerProps) {
  return (
    <div
      className={`pane-resizer ${isResizing ? 'resizing' : ''}`}
      role="separator"
      aria-orientation="vertical"
      aria-label="ペインの幅を変更（ダブルクリックで既定に戻す）"
      title="ドラッグで幅を変更 / ダブルクリックで既定に戻す"
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      onDoubleClick={onReset}
    >
      <span className="pane-resizer-grip" aria-hidden="true" />
    </div>
  )
}

import type { ViewMode } from '../hooks/useViewMode'

type ViewControlsProps = {
  mode: ViewMode
  size: number
  sizeMin: number
  sizeMax: number
  onModeChange: (mode: ViewMode) => void
  onSizeChange: (size: number) => void
  showSize?: boolean
}

export function ViewControls({
  mode,
  size,
  sizeMin,
  sizeMax,
  onModeChange,
  onSizeChange,
  showSize = true,
}: ViewControlsProps) {
  return (
    <div className="view-controls" role="toolbar" aria-label="表示設定">
      <div className="view-mode-group" role="group" aria-label="表示モード">
        <button
          type="button"
          className={`view-mode-button ${mode === 'grid' ? 'active' : ''}`}
          onClick={() => onModeChange('grid')}
          aria-pressed={mode === 'grid'}
          title="カードビュー"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1" fill="currentColor" />
            <rect x="9" y="1.5" width="5.5" height="5.5" rx="1" fill="currentColor" />
            <rect x="1.5" y="9" width="5.5" height="5.5" rx="1" fill="currentColor" />
            <rect x="9" y="9" width="5.5" height="5.5" rx="1" fill="currentColor" />
          </svg>
          <span>カード</span>
        </button>
        <button
          type="button"
          className={`view-mode-button ${mode === 'list' ? 'active' : ''}`}
          onClick={() => onModeChange('list')}
          aria-pressed={mode === 'list'}
          title="リストビュー"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <rect x="1.5" y="2.5" width="13" height="2" rx="1" fill="currentColor" />
            <rect x="1.5" y="7" width="13" height="2" rx="1" fill="currentColor" />
            <rect x="1.5" y="11.5" width="13" height="2" rx="1" fill="currentColor" />
          </svg>
          <span>リスト</span>
        </button>
      </div>
      {showSize && mode === 'grid' && (
        <label className="size-control" title="サムネイルサイズ">
          <span className="size-icon" aria-hidden="true">A</span>
          <input
            type="range"
            min={sizeMin}
            max={sizeMax}
            step={10}
            value={size}
            onChange={(e) => onSizeChange(Number(e.target.value))}
            aria-label="サムネイルサイズ"
          />
          <span className="size-value">{size}px</span>
        </label>
      )}
    </div>
  )
}

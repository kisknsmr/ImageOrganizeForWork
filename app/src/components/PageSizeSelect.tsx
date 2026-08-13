import { PAGE_SIZE_OPTIONS } from '../hooks/usePageSize'
import type { PageSizeSetting } from '../hooks/usePageSize'

type PageSizeSelectProps = {
  value: PageSizeSetting
  /** 'auto' のときに実際に使われている件数（表示用） */
  resolved: number
  onChange: (value: PageSizeSetting) => void
  disabled?: boolean
}

/** 1 ページの表示枚数を切り替える。変更すると先頭ページへ戻る */
export function PageSizeSelect({ value, resolved, onChange, disabled }: PageSizeSelectProps) {
  return (
    <label className="page-size-select" title="1ページに表示する枚数">
      <span className="page-size-label">表示</span>
      <select
        className="input"
        value={String(value)}
        onChange={(e) => onChange(e.target.value === 'auto' ? 'auto' : Number(e.target.value))}
        disabled={disabled}
        aria-label="1ページの表示枚数"
      >
        <option value="auto">自動 ({resolved})</option>
        {PAGE_SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size} 枚
          </option>
        ))}
      </select>
    </label>
  )
}

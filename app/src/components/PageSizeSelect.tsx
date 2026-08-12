import { PAGE_SIZE_OPTIONS } from '../hooks/usePageSize'

type PageSizeSelectProps = {
  value: number
  onChange: (value: number) => void
  disabled?: boolean
}

/** 1 ページの表示枚数を切り替える。変更すると先頭ページへ戻る */
export function PageSizeSelect({ value, onChange, disabled }: PageSizeSelectProps) {
  return (
    <label className="page-size-select" title="1ページに表示する枚数">
      <span className="page-size-label">表示</span>
      <select
        className="input"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        aria-label="1ページの表示枚数"
      >
        {PAGE_SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size} 枚
          </option>
        ))}
      </select>
    </label>
  )
}

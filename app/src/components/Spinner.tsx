type SpinnerProps = {
  size?: number
  inline?: boolean
  label?: string
}

export function Spinner({ size = 16, inline = false, label }: SpinnerProps) {
  const style = {
    width: `${size}px`,
    height: `${size}px`,
    borderWidth: `${Math.max(2, Math.round(size / 8))}px`,
  } as const

  return (
    <span className={`spinner ${inline ? 'spinner-inline' : ''}`} role="status" aria-live="polite">
      <span className="spinner-ring" style={style} aria-hidden="true" />
      {label ? <span className="spinner-label">{label}</span> : <span className="sr-only">読み込み中</span>}
    </span>
  )
}

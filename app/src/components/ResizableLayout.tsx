import type { CSSProperties, ReactNode } from 'react'
import type { useResizablePane } from '../hooks/useResizablePane'

type ResizableLayoutProps = {
  /** gallery-layout / workspace などのレイアウトクラス */
  className: string
  pane: ReturnType<typeof useResizablePane>
  children: ReactNode
}

/**
 * サイドペインをリサイズできるレイアウトコンテナ。
 *
 * 幅が未設定（null）の間は CSS の既定値がそのまま効き、ビューポート幅に追従する。
 * ドラッグで決めた幅がある場合だけ --side-pane-width を上書きする。
 */
export function ResizableLayout({ className, pane, children }: ResizableLayoutProps) {
  const { setContainer, width } = pane
  const style =
    width != null ? ({ ['--side-pane-width' as string]: `${width}px` } as CSSProperties) : undefined

  return (
    <div className={className} ref={setContainer} style={style}>
      {children}
    </div>
  )
}

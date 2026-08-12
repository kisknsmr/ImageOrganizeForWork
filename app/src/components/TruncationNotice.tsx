import type { TruncationInfo } from '../types'

type TruncationNoticeProps = {
  info?: TruncationInfo
  /** 実際に表示・処理できている件数 */
  shown: number
  /** 「〜が N 件あります」の主語（例: 'ぼけ候補'） */
  subject: string
  /** 上限を広げる手段の案内（任意） */
  hint?: string
}

/**
 * 一覧が上限で打ち切られたことを明示する。
 * 黙って省略すると、表示件数が「全件」に見えてしまうため。
 */
export function TruncationNotice({ info, shown, subject, hint }: TruncationNoticeProps) {
  if (!info?.truncated) return null
  return (
    <p className="muted analyze-note">
      {subject}は {info.available} 件ありますが、上限 {info.limit} 件のため {shown} 件のみ扱っています。
      {hint ? ` ${hint}` : ''}
    </p>
  )
}

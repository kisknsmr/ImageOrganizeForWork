import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { FileItem } from '../types'
import { formatFileSize, formatTimestamp } from '../utils/format'

type PreviewPaneProps = {
  /** 選択中のファイル。null なら案内文を出す */
  item: FileItem | null
  emptyMessage?: string
}

/**
 * プレビューとファイル情報のサブペイン。
 *
 * PyQt 版のプレビューパネルと同じ項目（プレビュー / ファイル名 / パス /
 * ファイルサイズ / 画像サイズ）を出す。サイズと寸法はディスクの実値を
 * API から取り直すので、スキャン後に差し替えられたファイルでも実態と一致する。
 */
export function PreviewPane({
  item,
  emptyMessage = '画像を選択してください（Ctrl/⌘+クリックで複数選択）',
}: PreviewPaneProps) {
  const info = useQuery({
    queryKey: ['file-info', item?.id],
    queryFn: () => api.fileInfo(item!.id),
    enabled: item != null,
  })

  if (!item) {
    return (
      <aside className="preview-pane" aria-label="プレビュー">
        <p className="muted">{emptyMessage}</p>
      </aside>
    )
  }

  const data = info.data
  const isVideo = (data?.content_type ?? item.content_type) === 'video'
  // 取得できるまでは DB の値を出しておく（毎回空欄が挟まると読みづらい）
  const size = data?.size ?? item.size
  const missing = data != null && !data.exists

  return (
    <aside className="preview-pane" aria-label="プレビュー">
      <h3 className="section-title preview-filename" title={item.filename}>
        {item.filename}
      </h3>

      <img src={api.previewUrl(item.id)} alt={item.filename} />

      <dl className="preview-info">
        <div className="preview-row">
          <dt>サイズ</dt>
          <dd>{formatFileSize(size)}</dd>
        </div>
        <div className="preview-row">
          <dt>{isVideo ? '解像度' : '画像サイズ'}</dt>
          <dd>
            {data?.width && data?.height ? (
              `${data.width.toLocaleString()} × ${data.height.toLocaleString()} px`
            ) : info.isPending ? (
              '読み込み中...'
            ) : (
              '—'
            )}
          </dd>
        </div>
        <div className="preview-row">
          <dt>種類</dt>
          <dd>{item.extension || (isVideo ? '動画' : '画像')}</dd>
        </div>
        <div className="preview-row">
          <dt>更新日時</dt>
          <dd>{formatTimestamp(data?.mtime ?? item.mtime)}</dd>
        </div>
      </dl>

      <div className="preview-path">
        <p className="kpi-label">パス</p>
        <p className="mono">{item.path}</p>
      </div>

      {missing && (
        <p className="preview-missing">ファイルが見つかりません（移動または削除された可能性があります）</p>
      )}
    </aside>
  )
}

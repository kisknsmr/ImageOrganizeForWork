import { api } from '../api/client'
import type { FileItem } from '../types'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(mtime: number): string {
  if (!mtime) return '-'
  return new Date(mtime * 1000).toLocaleString('ja-JP', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

type Props = {
  item: FileItem | null
  placeholder?: string
}

export function FileDetailPane({ item, placeholder = 'サムネイルをクリックして詳細表示' }: Props) {
  if (!item) {
    return (
      <aside className="preview-pane">
        <p className="muted" style={{ padding: 16 }}>{placeholder}</p>
      </aside>
    )
  }

  return (
    <aside className="preview-pane file-detail-pane">
      <img
        src={api.previewUrl(item.id)}
        alt={item.filename}
        className="file-detail-preview"
      />
      <div className="file-detail-info">
        <h3 className="file-detail-name" title={item.filename}>{item.filename}</h3>
        <table className="file-detail-table">
          <tbody>
            <tr>
              <th>サイズ</th>
              <td>{formatBytes(item.size)}</td>
            </tr>
            <tr>
              <th>更新日時</th>
              <td>{formatDate(item.mtime)}</td>
            </tr>
            <tr>
              <th>種類</th>
              <td>{item.content_type ?? item.extension}</td>
            </tr>
            {item.blur_score != null && (
              <tr>
                <th>ブレスコア</th>
                <td>{item.blur_score.toFixed(2)}</td>
              </tr>
            )}
            {item.triage_status && (
              <tr>
                <th>トリアージ</th>
                <td>{item.triage_status}</td>
              </tr>
            )}
            <tr>
              <th>パス</th>
              <td className="mono" style={{ fontSize: 10, wordBreak: 'break-all' }}>{item.path}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </aside>
  )
}

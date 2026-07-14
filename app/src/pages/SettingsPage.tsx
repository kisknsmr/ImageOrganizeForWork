import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'

export function SettingsPage() {
  const toast = useToast()
  // null = 未編集（サーバー値を表示）。編集した時だけ state に持つ
  const [trashFolderInput, setTrashFolderInput] = useState<string | null>(null)

  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const trashFolder = trashFolderInput ?? settings.data?.trash_folder ?? ''

  const saveMutation = useMutation({
    mutationFn: (folder: string) => api.updateSettings({ trash_folder: folder }),
    onSuccess: async () => {
      toast.success('設定を保存しました', 'Settings')
      setTrashFolderInput(null)
      await settings.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '設定の保存に失敗しました')
    },
  })

  const data = settings.data

  return (
    <section className="page">
      <header className="page-header">
        <h2>Settings</h2>
        <p className="page-subtitle">ライブラリ情報と既定値を確認し、ゴミ箱フォルダを設定できます。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {data ? `v${data.version}` : 'Loading...'}
          </span>
        </div>
      </div>

      <article className="card">
        <QueryState
          isLoading={settings.isPending}
          isError={settings.isError}
          error={settings.error}
          isEmpty={false}
          loadingMessage="設定を読み込み中..."
        />
      </article>

      {data && (
        <>
          <article className="card">
            <h3>ライブラリ</h3>
            <div className="card-grid">
              <div>
                <p className="kpi-label">総ファイル数</p>
                <p className="stat-value">{data.stats.total}</p>
              </div>
              <div>
                <p className="kpi-label">解析済み</p>
                <p className="stat-value">{data.stats.analyzed}</p>
              </div>
              <div>
                <p className="kpi-label">未解析</p>
                <p className="stat-value">{data.stats.unprocessed}</p>
              </div>
              <div>
                <p className="kpi-label">ゴミ箱</p>
                <p className="stat-value">{data.stats.trashed}</p>
              </div>
            </div>
            <p className="muted">ルートフォルダ: {data.root_path ?? '未設定'}</p>
            <p className="muted">データベース: {data.db_name}</p>
          </article>

          <article className="card">
            <h3>ゴミ箱フォルダ</h3>
            <div className="row">
              <input
                className="input"
                value={trashFolder}
                onChange={(e) => setTrashFolderInput(e.target.value)}
                placeholder="ゴミ箱の移動先フォルダ"
                disabled={saveMutation.isPending}
                style={{ flex: 1 }}
              />
              <button
                className="button"
                disabled={saveMutation.isPending || !trashFolder.trim() || trashFolder === data.trash_folder}
                onClick={() => saveMutation.mutate(trashFolder.trim())}
              >
                {saveMutation.isPending ? <Spinner size={14} inline /> : null}
                保存
              </button>
            </div>
          </article>

          <article className="card">
            <h3>既定値</h3>
            <p className="muted">ぼけしきい値: {data.defaults.blur_threshold}</p>
            <p className="muted">
              類似距離: {data.defaults.similarity_threshold}（最大 {data.defaults.max_similarity_distance}）
            </p>
            <p className="muted">低容量しきい値: {data.defaults.min_file_size_kb} KB</p>
          </article>

          <article className="card">
            <h3>対応拡張子</h3>
            <p className="muted">画像 ({data.extensions.image.length}): {data.extensions.image.join(', ')}</p>
            <p className="muted">動画 ({data.extensions.video.length}): {data.extensions.video.join(', ')}</p>
          </article>
        </>
      )}
    </section>
  )
}

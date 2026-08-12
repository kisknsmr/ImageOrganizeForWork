import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { useClearLibrary } from '../components/useClearLibrary'
import { getApiErrorMessage, useToast } from '../components/useToast'

export function SettingsPage() {
  const toast = useToast()
  const clearLibrary = useClearLibrary()
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

      {/* QueryState は該当状態のときだけ描画されるので、空カードで包まない */}
      <QueryState
        isLoading={settings.isPending}
        isError={settings.isError}
        error={settings.error}
        isEmpty={false}
        loadingMessage="設定を読み込み中..."
      />


      {data && (
        <>
          <article className="card">
            <h3>Library</h3>
            <div className="card-grid">
              <div>
                <p className="kpi-label">Total Files</p>
                <p className="stat-value">{data.stats.total}</p>
              </div>
              <div>
                <p className="kpi-label">Analyzed</p>
                <p className="stat-value">{data.stats.analyzed}</p>
              </div>
              <div>
                <p className="kpi-label">Unprocessed</p>
                <p className="stat-value">{data.stats.unprocessed}</p>
              </div>
              <div>
                <p className="kpi-label">In Trash</p>
                <p className="stat-value">{data.stats.trashed}</p>
              </div>
            </div>
            <p className="muted">ルートフォルダ: {data.root_path ?? '未設定'}</p>
            <p className="muted">データベース: {data.db_name}</p>
          </article>

          <article className="card">
            <h3>Trash Folder</h3>
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
                Save
              </button>
            </div>
          </article>

          <article className="card">
            <h3>Defaults</h3>
            <p className="muted">ぼけしきい値: {data.defaults.blur_threshold}</p>
            <p className="muted">
              類似距離: {data.defaults.similarity_threshold}（最大 {data.defaults.max_similarity_distance}）
            </p>
            <p className="muted">低容量しきい値: {data.defaults.min_file_size_kb} KB</p>
          </article>

          <article className="card">
            <h3>Supported Extensions</h3>
            <p className="muted">画像 ({data.extensions.image.length}): {data.extensions.image.join(', ')}</p>
            <p className="muted">動画 ({data.extensions.video.length}): {data.extensions.video.join(', ')}</p>
          </article>

          <article className="card danger-zone">
            <h3>読み込み記録の消去</h3>
            <p className="muted">
              スキャンで取り込んだファイル記録とサムネイルを DB から消します。
              <strong>ディスク上の画像ファイルは削除されません</strong>（再スキャンで元に戻せます）。
              ゴミ箱に入れたファイルの記録は、消すと復元できなくなるため残します。
            </p>
            <div className="row">
              <button
                className="button danger"
                type="button"
                disabled={clearLibrary.isPending || data.stats.total === 0}
                onClick={() =>
                  clearLibrary.clear('current', {
                    total: data.stats.total,
                    rootPath: data.root_path,
                  })
                }
              >
                {clearLibrary.isPending ? <Spinner size={14} inline /> : null}
                現在のライブラリをクリア（{data.stats.total.toLocaleString()} 件）
              </button>
              <button
                className="button ghost"
                type="button"
                disabled={clearLibrary.isPending}
                onClick={() => clearLibrary.clear('all', {})}
                title="過去に別フォルダをスキャンした記録もまとめて消します"
              >
                すべての読み込み記録をクリア
              </button>
            </div>
          </article>
        </>
      )}
    </section>
  )
}

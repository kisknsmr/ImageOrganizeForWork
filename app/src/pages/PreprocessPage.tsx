import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { FolderPicker } from '../components/FolderPicker'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { useJobStatus } from '../components/useJobStatus'
import { getApiErrorMessage, useToast } from '../components/useToast'

export function PreprocessPage() {
  const toast = useToast()
  const [rootPath, setRootPath] = useState('')
  const { status, jobRunning, jobKindLabel, refetchStatus } = useJobStatus()

  const startPreprocess = useMutation({
    mutationFn: async () => {
      const confirmed = window.confirm(
        `「${rootPath}」直下のファイルを画像/動画/その他に振り分けます。\n` +
          '  01 Pictures ／ 02 Movies ／ 03 Others\n' +
          '元のサブフォルダ構成はそれぞれの下に保たれます（ファイルの移動です）。実行しますか？',
      )
      if (!confirmed) return null
      return api.preprocessStart(rootPath)
    },
    onSuccess: (res) => {
      if (res) {
        toast.success('振り分けを開始しました', 'Preprocess')
        refetchStatus()
      }
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '振り分け開始に失敗しました')
    },
  })

  const busy = startPreprocess.isPending || jobRunning

  return (
    <section className="page">
      <header className="page-header">
        <h2>Preprocess</h2>
        <p className="page-subtitle">
          取込前のフォルダを画像/動画/その他に振り分けます。サブフォルダ構成はそのまま保たれます。
        </p>
      </header>
      {jobRunning && (
        <div className="toolbar">
          <div className="toolbar-group">
            <span className="status-chip">
              <span className="status-dot" />
              {jobKindLabel}
            </span>
            <span className="muted">{status.data?.message}</span>
            <span className="muted">{status.data?.percent ?? 0}%</span>
            {(status.data?.total ?? 0) > 0 && (
              <span className="muted">
                {status.data?.current ?? 0}/{status.data?.total}
              </span>
            )}
          </div>
          {(status.data?.percent ?? 0) === 0 ? (
            <progress max={100} />
          ) : (
            <progress value={status.data?.percent ?? 0} max={100} />
          )}
        </div>
      )}
      {!jobRunning && status.data?.kind === 'preprocess' && status.data?.result && (
        <article className="card result-card">
          <h3>振り分け結果</h3>
          <div className="card-grid">
            <div>
              <p className="kpi-label">Pictures</p>
              <p className="stat-value">{status.data.result.pictures}</p>
            </div>
            <div>
              <p className="kpi-label">Movies</p>
              <p className="stat-value">{status.data.result.movies}</p>
            </div>
            <div>
              <p className="kpi-label">Others</p>
              <p className="stat-value">{status.data.result.others}</p>
            </div>
            <div>
              <p className="kpi-label">Skipped</p>
              <p className="stat-value">{status.data.result.skipped}</p>
            </div>
          </div>
          <p className="muted">
            対象{status.data.result.total}件中、{status.data.result.moved}件を移動しました
            {status.data.result.skipped > 0
              ? `（同名ファイルが既にあり${status.data.result.skipped}件はスキップしました）`
              : ''}
            。
          </p>
        </article>
      )}
      <article className="card">
        <QueryState
          isLoading={status.isPending}
          isError={status.isError}
          error={status.error}
          isEmpty={false}
          loadingMessage="ジョブ状態を確認中..."
        />
        <FolderPicker value={rootPath} onChange={setRootPath} disabled={busy} />
        <div className="row">
          <button
            className="button"
            type="button"
            disabled={!rootPath || busy}
            onClick={() => startPreprocess.mutate()}
            title="画像/動画/その他フォルダへ振り分け（フォルダ構成は保持）"
          >
            {startPreprocess.isPending ? <Spinner size={14} inline /> : null}
            Sort into Pictures/Movies/Others
          </button>
        </div>
        <p className="muted">
          01 Pictures / 02 Movies / 03 Others 以外のフォルダの中身も対象になります（フォルダ自体は空のまま残ります）。
        </p>
        {status.data?.error && <p className="muted analyze-note">エラー: {status.data.error}</p>}
      </article>
    </section>
  )
}

import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { FolderPicker } from '../components/FolderPicker'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { useJobStatus } from '../components/useJobStatus'
import { getApiErrorMessage, useToast } from '../components/useToast'
import type { PreprocessMode } from '../types'

export function PreprocessPage() {
  const toast = useToast()
  const [rootPath, setRootPath] = useState('')
  const [mode, setMode] = useState<PreprocessMode>('incremental')
  const { status, jobRunning, jobKindLabel, refetchStatus } = useJobStatus()

  const startPreprocess = useMutation({
    mutationFn: async () => {
      const scope =
        mode === 'full'
          ? '既に振り分け済みのファイルも分類を見直し、間違ったカテゴリにあるものは移し直します。\n'
          : 'カテゴリフォルダ(01/02/03)の中は対象外です（未振り分けのみ）。\n'
      const confirmed = window.confirm(
        `「${rootPath}」のファイルを画像/動画/その他に振り分けます。\n` +
          '  01 Pictures ／ 02 Movies ／ 03 Others\n' +
          scope +
          '元のサブフォルダ構成はそれぞれの下に保たれます（ファイルの移動です）。実行しますか？',
      )
      if (!confirmed) return null
      return api.preprocessStart(rootPath, mode)
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

  // 完了したジョブの結果はサーバー側に残り続けるので、明示的に破棄できるようにする
  const dismissResult = useMutation({
    mutationFn: api.jobsReset,
    onSuccess: () => refetchStatus(),
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '結果表示を消せませんでした')
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
          <div className="card-header">
            <h3>振り分け結果</h3>
            <button
              type="button"
              className="icon-button"
              title="この結果表示を消す"
              aria-label="結果を閉じる"
              disabled={dismissResult.isPending}
              onClick={() => dismissResult.mutate()}
            >
              ×
            </button>
          </div>
          {/* フォルダ全体を「移動した / 対応不要 / スキップ」に分解して示す。
              内訳の合計が全ファイル数と一致するので、数字を突き合わせられる */}
          <div className="card-grid">
            <div>
              <p className="kpi-label">全ファイル</p>
              <p className="stat-value">{status.data.result.all_files.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">移動した</p>
              <p className="stat-value">{status.data.result.moved.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">対応不要</p>
              <p className="stat-value">{status.data.result.already_sorted.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">スキップ</p>
              <p className="stat-value">{status.data.result.skipped.toLocaleString()}</p>
            </div>
          </div>
          <p className="muted">
            {status.data.result.full ? 'フル（見直しあり）' : '差分'}で実行。
            {status.data.result.rechecked > 0
              ? `うち ${status.data.result.rechecked.toLocaleString()}件は分類を見直して別カテゴリへ移し直しました。`
              : ''}
          </p>
          <p className="muted">
            移動の内訳: Pictures {status.data.result.pictures.toLocaleString()} ・ Movies{' '}
            {status.data.result.movies.toLocaleString()} ・ Others{' '}
            {status.data.result.others.toLocaleString()}
            {status.data.result.already_sorted > 0
              ? `。対応不要 ${status.data.result.already_sorted.toLocaleString()}件は既に振り分け済みのファイルです`
              : ''}
            {status.data.result.skipped > 0
              ? `。スキップ ${status.data.result.skipped.toLocaleString()}件は移動先に同名ファイルがありました`
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
        <FolderPicker
          value={rootPath}
          onChange={setRootPath}
          disabled={busy}
          countMode="preprocess"
          preprocessMode={mode}
        />
        <div className="row">
          <div className="view-mode-group" role="group" aria-label="走査モード">
            <button
              type="button"
              className={`view-mode-button ${mode === 'incremental' ? 'active' : ''}`}
              aria-pressed={mode === 'incremental'}
              onClick={() => setMode('incremental')}
              title="カテゴリフォルダの中は見ない。未振り分けのファイルだけを対象にする"
            >
              差分
            </button>
            <button
              type="button"
              className={`view-mode-button ${mode === 'full' ? 'active' : ''}`}
              aria-pressed={mode === 'full'}
              onClick={() => setMode('full')}
              title="振り分け済みのファイルも分類を見直し、間違ったカテゴリにあるものを移し直す"
            >
              フル（見直し）
            </button>
          </div>
        </div>
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
          {mode === 'full'
            ? '振り分け済みのファイルも分類を見直します。対応形式が増えた後（HEIC など）に、03 Others へ入ったままの画像を正しいカテゴリへ移せます。'
            : '01 Pictures / 02 Movies / 03 Others の中身は対象外です。未振り分けのファイルだけを移動します（フォルダ自体は空のまま残ります）。'}
        </p>
        {status.data?.error && <p className="muted analyze-note">エラー: {status.data.error}</p>}
      </article>
    </section>
  )
}

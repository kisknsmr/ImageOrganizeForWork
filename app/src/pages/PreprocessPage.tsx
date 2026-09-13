import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { FolderPicker } from '../components/FolderPicker'
import { JobControls } from '../components/JobControls'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { useJobStatus } from '../components/useJobStatus'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { isEmptyDirsResult, isPreprocessResult, type PreprocessMode } from '../types'

export function PreprocessPage() {
  const toast = useToast()
  const [rootPath, setRootPath] = useState('')
  const [mode, setMode] = useState<PreprocessMode>('incremental')
  const { status, jobRunning, jobKindLabel, refetchStatus } = useJobStatus()

  // 手入力の途中経過で走査を始めないよう、入力が落ち着いてから数える
  const [countedPath, setCountedPath] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setCountedPath(rootPath.trim()), 600)
    return () => clearTimeout(timer)
  }, [rootPath])

  // 空フォルダの事前カウント。実行中は数が変わるので止める
  const emptyDirs = useQuery({
    queryKey: ['emptyDirsCheck', countedPath],
    queryFn: () => api.emptyDirsCheck(countedPath),
    enabled: !!countedPath && !jobRunning,
  })

  // ジョブが終わると空フォルダの数は変わる（振り分けで空が増え、削除で減る）。
  // staleTime 内だと古い数が残って見えるので、終了を検知して数え直す。
  const wasRunning = useRef(false)
  const refetchEmptyDirs = emptyDirs.refetch
  useEffect(() => {
    if (wasRunning.current && !jobRunning && countedPath) refetchEmptyDirs()
    wasRunning.current = jobRunning
  }, [jobRunning, countedPath, refetchEmptyDirs])

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

  const removeEmptyDirs = useMutation({
    mutationFn: async () => {
      const found = emptyDirs.data?.total ?? 0
      const sample = (emptyDirs.data?.samples ?? []).slice(0, 10).join('\n  ')
      const more = found > (emptyDirs.data?.samples.length ?? 0) ? '\n  ...' : ''
      const confirmed = window.confirm(
        `「${rootPath}」の空フォルダ ${found.toLocaleString()} 個を削除します。\n` +
          '空フォルダだけが入れ子になっている場合は、何階層でもまとめて消えます。\n' +
          'ファイルが 1 つでも残っているフォルダは残します（ゴミ箱と 01/02/03 も残します）。\n' +
          (sample ? `\n削除するフォルダ:\n  ${sample}${more}\n` : '') +
          '\n実行しますか？',
      )
      if (!confirmed) return null
      return api.emptyDirsRemove(rootPath)
    },
    onSuccess: (res) => {
      if (res) {
        toast.success('空フォルダの削除を開始しました', 'Preprocess')
        refetchStatus()
      }
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '空フォルダ削除に失敗しました')
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

  const busy = startPreprocess.isPending || removeEmptyDirs.isPending || jobRunning

  // 結果の形はジョブ種別ごとに違うので、ここで 1 度だけ絞り込む
  const jobResult = jobRunning ? null : status.data?.result
  const preprocessResult =
    status.data?.kind === 'preprocess' && isPreprocessResult(jobResult) ? jobResult : null
  const emptyDirsResult =
    status.data?.kind === 'empty_dirs' && isEmptyDirsResult(jobResult) ? jobResult : null

  // 数え終わった対象が、いま入力されているフォルダと同じときだけ件数を信用する
  const emptyDirCount =
    countedPath && countedPath === rootPath.trim() && !emptyDirs.isFetching
      ? (emptyDirs.data?.total ?? null)
      : null

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
              {status.data?.paused ? '一時停止中' : jobKindLabel}
            </span>
            <span className="muted">{status.data?.message}</span>
            <span className="muted">{status.data?.percent ?? 0}%</span>
            {(status.data?.total ?? 0) > 0 && (
              <span className="muted">
                {status.data?.current ?? 0}/{status.data?.total}
              </span>
            )}
          </div>
          <JobControls paused={status.data?.paused ?? false} onChanged={refetchStatus} />
          {(status.data?.percent ?? 0) === 0 ? (
            <progress max={100} />
          ) : (
            <progress value={status.data?.percent ?? 0} max={100} />
          )}
        </div>
      )}
      {emptyDirsResult && (
        <article className="card result-card">
          <div className="card-header">
            <h3>空フォルダ削除の結果</h3>
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
          <div className="card-grid">
            <div>
              <p className="kpi-label">対象</p>
              <p className="stat-value">{emptyDirsResult.total.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">削除した</p>
              <p className="stat-value">{emptyDirsResult.removed.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">失敗</p>
              <p className="stat-value">{emptyDirsResult.failed.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">最大の深さ</p>
              <p className="stat-value">{emptyDirsResult.max_depth.toLocaleString()}</p>
            </div>
          </div>
          <p className="muted">
            {emptyDirsResult.stopped ? '中止しました。' : ''}
            入れ子になった空フォルダは深い方から削除するので、連なっていた分もまとめて消えています
            {emptyDirsResult.max_depth > 0
              ? `（いちばん深いもので ${emptyDirsResult.max_depth} 階層）`
              : ''}
            。
            {emptyDirsResult.junk_removed > 0
              ? `Thumbs.db などの残骸 ${emptyDirsResult.junk_removed.toLocaleString()}件も一緒に削除しました。`
              : ''}
            {emptyDirsResult.failed > 0
              ? `失敗 ${emptyDirsResult.failed.toLocaleString()}件は、削除直前に中身が増えたか、権限がありませんでした。`
              : ''}
          </p>
        </article>
      )}
      {preprocessResult && (
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
              <p className="stat-value">{preprocessResult.all_files.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">移動した</p>
              <p className="stat-value">{preprocessResult.moved.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">対応不要</p>
              <p className="stat-value">{preprocessResult.already_sorted.toLocaleString()}</p>
            </div>
            <div>
              <p className="kpi-label">スキップ</p>
              <p className="stat-value">{preprocessResult.skipped.toLocaleString()}</p>
            </div>
          </div>
          <p className="muted">
            {preprocessResult.full ? 'フル（見直しあり）' : '差分'}で実行。
            {preprocessResult.rechecked > 0
              ? `うち ${preprocessResult.rechecked.toLocaleString()}件は分類を見直して別カテゴリへ移し直しました。`
              : ''}
          </p>
          <p className="muted">
            移動の内訳: Pictures {preprocessResult.pictures.toLocaleString()} ・ Movies{' '}
            {preprocessResult.movies.toLocaleString()} ・ Others{' '}
            {preprocessResult.others.toLocaleString()}
            {preprocessResult.already_sorted > 0
              ? `。対応不要 ${preprocessResult.already_sorted.toLocaleString()}件は既に振り分け済みのファイルです`
              : ''}
            {preprocessResult.skipped > 0
              ? `。スキップ ${preprocessResult.skipped.toLocaleString()}件は移動先に同名ファイルがありました`
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
        {/* 振り分けの後は元のフォルダが空で残る。片付けは明示的な操作にして、
            ユーザーが中身を確認してから消せるようにする */}
        <div className="row">
          <button
            className="button danger"
            type="button"
            disabled={!rootPath || busy || !emptyDirCount}
            onClick={() => removeEmptyDirs.mutate()}
            title="中身のないフォルダを削除（入れ子になっていれば何階層でもまとめて）"
          >
            {removeEmptyDirs.isPending ? <Spinner size={14} inline /> : null}
            Delete empty folders
          </button>
          <span className="muted">
            {!rootPath
              ? 'フォルダを選ぶと空フォルダを数えます'
              : emptyDirs.isError
                ? '空フォルダを数えられませんでした'
                : emptyDirCount === null
                  ? '空フォルダを数えています...'
                  : emptyDirCount > 0
                    ? `空フォルダ ${emptyDirCount.toLocaleString()} 個` +
                      `（いちばん深いもので ${emptyDirs.data?.max_depth ?? 0} 階層）`
                    : '空フォルダはありません'}
          </span>
        </div>
        <p className="muted">
          空フォルダだけが入れ子になっている場合は、何階層でも深い方からまとめて削除します（a/b/c
          が全部空なら 3 つとも消えます）。ファイルが 1 つでも残っているフォルダは残します。ゴミ箱と
          直下の 01 Pictures / 02 Movies / 03 Others
          は、空でも受け皿として残します。Thumbs.db・desktop.ini
          などの残骸しか入っていないフォルダは、空とみなして残骸ごと削除します。
        </p>
        {status.data?.error && <p className="muted analyze-note">エラー: {status.data.error}</p>}
      </article>
    </section>
  )
}

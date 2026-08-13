import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { FolderPicker } from './FolderPicker'
import { JobControls } from './JobControls'
import { QueryState } from './QueryState'
import { Spinner } from './Spinner'
import { useJobStatus } from './useJobStatus'
import { getApiErrorMessage, useToast } from './useToast'

export function ImportPanel() {
  const toast = useToast()
  const [rootPath, setRootPath] = useState('')
  const [analyzeNote, setAnalyzeNote] = useState<string | null>(null)
  const { status, jobRunning, jobKindLabel, refetchStatus } = useJobStatus()

  const startScan = useMutation({
    mutationFn: async () => {
      const check = await api.scanCheck(rootPath)
      if (check.already_up_to_date) {
        const wantsReset = window.confirm(
          `このフォルダ（${check.total}件）は既に全て解析済みです。\n未解析の状態に戻して再解析しますか？`,
        )
        if (wantsReset) {
          await api.analyzeReset(rootPath)
          toast.info(`${check.total}件を未解析に戻しました`, 'Import')
        }
      }
      return api.scanStart(rootPath)
    },
    onSuccess: () => {
      setAnalyzeNote(null)
      toast.success('スキャンを開始しました', 'Import')
      refetchStatus()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'スキャン開始に失敗しました')
    },
  })

  const startAnalyze = useMutation({
    mutationFn: api.analyzeStart,
    onSuccess: (res) => {
      if (res.started) {
        setAnalyzeNote(null)
        toast.success('解析を開始しました', 'Analyze')
        refetchStatus()
      } else {
        const message = res.message ?? '解析は開始されませんでした'
        setAnalyzeNote(message)
        toast.show({ message, title: 'Analyze', variant: 'warning', duration: 6000 })
      }
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '解析開始に失敗しました')
    },
  })

  // バックグラウンドでスキャン/解析/振り分けが走っている間は二重起動(409)を防ぐ
  const busy = startScan.isPending || startAnalyze.isPending || jobRunning

  return (
    <>
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
            // 探索フェーズは総数不明のため不確定バー（value 省略でアニメーション）
            <progress max={100} />
          ) : (
            <progress value={status.data?.percent ?? 0} max={100} />
          )}
        </div>
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
            onClick={() => startScan.mutate()}
          >
            {startScan.isPending ? <Spinner size={14} inline /> : null}
            Start Scan
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={busy}
            onClick={() => startAnalyze.mutate()}
          >
            {startAnalyze.isPending ? <Spinner size={14} inline /> : null}
            Start Analyze
          </button>
        </div>
        {status.data?.error && <p className="muted analyze-note">エラー: {status.data.error}</p>}
        {analyzeNote && <p className="muted analyze-note">{analyzeNote}</p>}
      </article>
    </>
  )
}

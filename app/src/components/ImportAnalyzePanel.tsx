import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { QueryState } from './QueryState'
import { Spinner } from './Spinner'
import { getApiErrorMessage, useToast } from './useToast'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function pickFolder(): Promise<string | null> {
  if (!isTauri) return null
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({ directory: true, multiple: false })
  if (typeof selected === 'string') return selected
  return null
}

export function ImportAnalyzePanel() {
  const toast = useToast()
  const [rootPath, setRootPath] = useState('')
  const status = useQuery({ queryKey: ['scanStatus'], queryFn: api.scanStatus, refetchInterval: 1000 })

  const startScan = useMutation({
    mutationFn: async () => api.scanStart(rootPath),
    onSuccess: () => toast.success('スキャンを開始しました', 'Import'),
    onError: (error) => toast.error(getApiErrorMessage(error), 'スキャン開始に失敗しました'),
  })

  const stopJob = useMutation({
    mutationFn: api.jobStop,
    onSuccess: (res) => {
      if (res.ok) toast.success(res.message, 'Stop')
      else toast.info(res.message, 'Stop')
    },
    onError: (error) => toast.error(getApiErrorMessage(error), '中止に失敗しました'),
  })

  const startAnalyze = useMutation({
    mutationFn: api.analyzeStart,
    onSuccess: (res) => {
      if (res.started) {
        toast.success('解析を開始しました', 'Analyze')
      } else {
        toast.warning(res.message ?? '解析は開始されませんでした', 'Analyze')
      }
    },
    onError: (error) => toast.error(getApiErrorMessage(error), '解析開始に失敗しました'),
  })

  const handlePickFolder = async () => {
    const path = await pickFolder()
    if (path) setRootPath(path)
  }

  const busy = startScan.isPending || startAnalyze.isPending
  const running = status.data?.running ?? false
  const percent = status.data?.percent ?? 0

  return (
    <section className="dashboard-section">
      <h3 className="section-title">Import &amp; Analyze</h3>
      <article className="card">
        <QueryState
          isLoading={status.isPending}
          isError={status.isError}
          error={status.error}
          isEmpty={false}
          loadingMessage="ジョブ状態を確認中..."
        />
        <div className="import-panel-layout">
          <div className="import-path-row">
            <label className="label" htmlFor="dashboard-root-path">Root Folder</label>
            <div className="row">
              <input
                id="dashboard-root-path"
                className="input"
                value={rootPath}
                onChange={(e) => setRootPath(e.target.value)}
                placeholder="D:/Pictures"
                disabled={busy}
              />
              {isTauri && (
                <button className="button ghost" type="button" onClick={handlePickFolder} disabled={busy} title="フォルダを選択">
                  参照...
                </button>
              )}
            </div>
          </div>
          <div className="import-actions-row">
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
            {running && (
              <button
                className="button danger"
                type="button"
                disabled={stopJob.isPending}
                onClick={() => stopJob.mutate()}
                title="現在のファイル処理が完了次第、停止します"
              >
                {stopJob.isPending ? <Spinner size={14} inline /> : null}
                中止
              </button>
            )}
            <span className="status-chip" style={{ marginLeft: 'auto' }}>
              <span className="status-dot" style={{ background: running ? 'var(--success)' : 'var(--text-muted)' }} />
              {running ? `Running ${percent}%` : 'Idle'}
              {!running && percent === 100 && <span className="muted" style={{ fontSize: 11, marginLeft: 4 }}>前回完了</span>}
            </span>
          </div>
        </div>
        {(running || percent > 0) && (
          <>
            <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>{status.data?.message ?? '待機中'}</p>
            <progress value={percent} max={100} style={{ marginTop: 6 }} />
          </>
        )}
      </article>
    </section>
  )
}

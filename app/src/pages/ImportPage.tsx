import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'

// Tauri 環境かどうかを判定
const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function pickFolder(): Promise<string | null> {
  if (!isTauri) return null
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({ directory: true, multiple: false })
  if (typeof selected === 'string') return selected
  return null
}

export function ImportPage() {
  const toast = useToast()
  const [rootPath, setRootPath] = useState('')
  const status = useQuery({
    queryKey: ['scanStatus'],
    queryFn: api.scanStatus,
    // 実行中は細かく、待機中は控えめにポーリングする
    refetchInterval: (query) => (query.state.data?.running ? 400 : 2000),
  })

  const startScan = useMutation({
    mutationFn: async () => api.scanStart(rootPath),
    onSuccess: () => {
      toast.success('スキャンを開始しました', 'Import')
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'スキャン開始に失敗しました')
    },
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
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '解析開始に失敗しました')
    },
  })

  const handlePickFolder = async () => {
    const path = await pickFolder()
    if (path) setRootPath(path)
  }

  // バックグラウンドでスキャン/解析が走っている間は二重起動(409)を防ぐ
  const jobRunning = status.data?.running ?? false
  const busy = startScan.isPending || startAnalyze.isPending || jobRunning

  return (
    <section className="page">
      <header className="page-header">
        <h2>Import And Analyze</h2>
        <p className="page-subtitle">ルートフォルダを指定してスキャンし、続けて解析を実行します。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {jobRunning ? (status.data?.kind === 'analyze' ? '解析中' : 'スキャン中') : '待機中'}
          </span>
          <span className="muted">{status.data?.percent ?? 0}%</span>
          {(status.data?.total ?? 0) > 0 && (
            <span className="muted">
              {status.data?.current ?? 0}/{status.data?.total}
            </span>
          )}
        </div>
      </div>
      <article className="card">
        <QueryState
          isLoading={status.isPending}
          isError={status.isError}
          error={status.error}
          isEmpty={false}
          loadingMessage="ジョブ状態を確認中..."
        />
        <label className="label" htmlFor="root-path">
          Root Folder
        </label>
        <div className="row">
          <input
            id="root-path"
            className="input"
            value={rootPath}
            onChange={(e) => setRootPath(e.target.value)}
            placeholder="D:/Pictures"
            disabled={busy}
          />
          {isTauri && (
            <button
              className="button ghost"
              type="button"
              onClick={handlePickFolder}
              disabled={busy}
              title="フォルダを選択"
            >
              参照...
            </button>
          )}
        </div>
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
        <p className="muted">
          {status.data?.error ? `エラー: ${status.data.error}` : (status.data?.message ?? '待機中')}
        </p>
        {jobRunning && (status.data?.percent ?? 0) === 0 ? (
          // 探索フェーズは総数不明のため不確定バー（value 省略でアニメーション）
          <progress max={100} />
        ) : (
          <progress value={status.data?.percent ?? 0} max={100} />
        )}
      </article>
    </section>
  )
}

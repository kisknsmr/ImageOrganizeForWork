import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'

export function ImportPage() {
  const [rootPath, setRootPath] = useState('')
  const status = useQuery({ queryKey: ['scanStatus'], queryFn: api.scanStatus, refetchInterval: 1000 })

  const startScan = useMutation({
    mutationFn: async () => api.scanStart(rootPath),
  })
  const startAnalyze = useMutation({
    mutationFn: api.analyzeStart,
  })

  return (
    <section className="page">
      <h2>Import And Analyze</h2>
      <article className="card">
        <label className="label" htmlFor="root-path">
          Root Folder
        </label>
        <input
          id="root-path"
          className="input"
          value={rootPath}
          onChange={(e) => setRootPath(e.target.value)}
          placeholder="D:/Pictures"
        />
        <div className="row">
          <button className="button" type="button" disabled={!rootPath || startScan.isPending} onClick={() => startScan.mutate()}>
            Start Scan
          </button>
          <button className="button secondary" type="button" disabled={startAnalyze.isPending} onClick={() => startAnalyze.mutate()}>
            Start Analyze
          </button>
        </div>
        <p className="muted">{status.data?.message ?? '待機中'}</p>
        <progress value={status.data?.percent ?? 0} max={100} />
      </article>
    </section>
  )
}


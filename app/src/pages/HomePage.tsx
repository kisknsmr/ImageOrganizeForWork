import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'

export function HomePage() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 3000 })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 3000 })
  const hasError = stats.isError || health.isError

  return (
    <section className="page">
      <header className="page-header">
        <h2>PhotoSortX Dashboard</h2>
        <p className="page-subtitle">既存PyQt版の機能を維持しながら、Tauri版へ段階移行しています。</p>
      </header>
      <QueryState
        isLoading={stats.isPending || health.isPending}
        isError={hasError}
        error={stats.error ?? health.error}
        isEmpty={false}
        loadingMessage="ダッシュボードを読み込み中..."
      />
      {!stats.isPending && !health.isPending && !hasError && (
        <>
          <div className="card-grid">
            <article className="card">
              <h3>API Status</h3>
              <p>{health.data?.ok ? 'Online' : 'Offline'}</p>
              <small className="muted">version: {health.data?.version ?? '-'}</small>
            </article>
            <article className="card">
              <h3>Total Files</h3>
              <p>{stats.data?.total ?? 0}</p>
            </article>
            <article className="card">
              <h3>Analyzed</h3>
              <p>{stats.data?.analyzed ?? 0}</p>
            </article>
            <article className="card">
              <h3>Triaged</h3>
              <p>{stats.data?.triaged ?? 0}</p>
            </article>
          </div>
          <div className="card-grid">
            <article className="card">
              <h3>Unprocessed</h3>
              <p>{stats.data?.unprocessed ?? 0}</p>
            </article>
            <article className="card">
              <h3>In Trash</h3>
              <p>{stats.data?.trashed ?? 0}</p>
            </article>
            <article className="card wide">
              <h3>Root Path</h3>
              <p className="mono">{stats.data?.root_path ?? '未設定'}</p>
            </article>
          </div>
        </>
      )}
    </section>
  )
}


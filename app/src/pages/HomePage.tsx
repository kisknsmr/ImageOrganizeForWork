import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { CleanupSummaryPanel } from '../components/CleanupSummaryPanel'
import { ImportAnalyzePanel } from '../components/ImportAnalyzePanel'
import { QueryState } from '../components/QueryState'

export function HomePage() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 3000 })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 3000 })
  const hasError = stats.isError || health.isError

  return (
    <section className="page">
      <header className="page-header">
        <h2>Dashboard</h2>
        <p className="page-subtitle">ライブラリの概要・取込・解析・整理サマリーをひとまとめに確認できます。</p>
      </header>

      {/* KPI カード */}
      <section className="dashboard-section">
        <h3 className="section-title">Library Overview</h3>
        <QueryState
          isLoading={stats.isPending || health.isPending}
          isError={hasError}
          error={stats.error ?? health.error}
          isEmpty={false}
          loadingMessage="ダッシュボードを読み込み中..."
        />
        {!stats.isPending && !health.isPending && !hasError && (
          <div className="card-grid card-grid--tiles">
            <article className="card card-tile">
              <p className="kpi-label muted">API Status</p>
              <p className="stat-value" style={{ fontSize: 22, color: health.data?.ok ? 'var(--success)' : 'var(--danger)' }}>
                {health.data?.ok ? 'Online' : 'Offline'}
              </p>
              <small className="muted">v{health.data?.version ?? '-'}</small>
            </article>
            <article className="card card-tile">
              <p className="kpi-label muted">Total Files</p>
              <p className="stat-value">{stats.data?.total ?? 0}</p>
            </article>
            <article className="card card-tile">
              <p className="kpi-label muted">Analyzed</p>
              <p className="stat-value">{stats.data?.analyzed ?? 0}</p>
            </article>
            <article className="card card-tile">
              <p className="kpi-label muted">In Trash</p>
              <p className="stat-value">{stats.data?.trashed ?? 0}</p>
            </article>
            <article className="card card-tile" style={{ gridColumn: 'span 2' }}>
              <p className="kpi-label muted">Root Path</p>
              <p className="mono" style={{ marginTop: 6, fontSize: 13 }}>{stats.data?.root_path ?? '未設定'}</p>
            </article>
            <article className="card card-tile">
              <p className="kpi-label muted">Unprocessed</p>
              <p className="stat-value">{stats.data?.unprocessed ?? 0}</p>
            </article>
            <article className="card card-tile">
              <p className="kpi-label muted">Triaged</p>
              <p className="stat-value">{stats.data?.triaged ?? 0}</p>
            </article>
          </div>
        )}
      </section>

      {/* Import & Analyze */}
      <ImportAnalyzePanel />

      {/* Clean Up Summary */}
      <CleanupSummaryPanel />
    </section>
  )
}

import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { ImportPanel } from '../components/ImportPanel'
import { QueryState } from '../components/QueryState'

type StatTileProps = {
  label: string
  value: number | string
  hint?: string
}

/** KPI タイル。見出しではなく数値を主役にし、補足は 1 行に抑える。 */
function StatTile({ label, value, hint }: StatTileProps) {
  return (
    <article className="card">
      <p className="kpi-label">{label}</p>
      <p className="stat-value">{typeof value === 'number' ? value.toLocaleString() : value}</p>
      {hint && <p className="muted md-body-small">{hint}</p>}
    </article>
  )
}

export function HomePage() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 3000 })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 3000 })
  const hasError = stats.isError || health.isError
  const ready = !stats.isPending && !health.isPending && !hasError

  return (
    <section className="page">
      <header className="page-header">
        <h2>Dashboard</h2>
        <p className="page-subtitle">
          対象フォルダを選んでスキャン・解析を実行します。件数はすべて現在のライブラリ配下の集計です。
        </p>
      </header>

      <ImportPanel />

      <QueryState
        isLoading={stats.isPending || health.isPending}
        isError={hasError}
        error={stats.error ?? health.error}
        isEmpty={false}
        loadingMessage="ダッシュボードを読み込み中..."
      />

      {ready && (
        <>
          <div className="card-grid">
            <StatTile label="Total files" value={stats.data?.total ?? 0} />
            <StatTile label="Analyzed" value={stats.data?.analyzed ?? 0} />
            <StatTile label="Triaged" value={stats.data?.triaged ?? 0} />
            <StatTile label="Unprocessed" value={stats.data?.unprocessed ?? 0} />
            <StatTile label="In trash" value={stats.data?.trashed ?? 0} />
            <StatTile
              label="API"
              value={health.data?.ok ? 'Online' : 'Offline'}
              hint={`version ${health.data?.version ?? '-'}`}
            />
          </div>

          <article className="card">
            <p className="kpi-label">Current library</p>
            <p className="mono">{stats.data?.root_path ?? '未設定'}</p>
            <p className="muted md-body-small">
              スキャン／解析の対象フォルダです。変更するには上の Selected Folder
              で別のフォルダを指定して Scan を実行してください。
            </p>
          </article>
        </>
      )}
    </section>
  )
}

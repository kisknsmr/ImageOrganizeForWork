import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function HomePage() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 3000 })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 3000 })

  return (
    <section className="page">
      <h2>Library Overview</h2>
      <div className="card-grid">
        <article className="card">
          <h3>API Health</h3>
          <p>{health.data?.ok ? 'Online' : 'Offline'}</p>
          <small>version: {health.data?.version ?? '-'}</small>
        </article>
        <article className="card">
          <h3>Total</h3>
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
      <article className="card">
        <h3>Root Path</h3>
        <p className="mono">{stats.data?.root_path ?? '未設定'}</p>
      </article>
    </section>
  )
}


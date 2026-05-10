import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { QueryState } from './QueryState'

type SummaryCardProps = {
  title: string
  count: number | string
  unit: string
  description: string
  to: string
  color: string
  loading?: boolean
}

function SummaryCard({ title, count, unit, description, to, color, loading }: SummaryCardProps) {
  return (
    <Link to={to} style={{ textDecoration: 'none' }}>
      <article className="card cleanup-summary-card card-tile" style={{ borderTop: `3px solid ${color}` }}>
        <h3 style={{ color, fontSize: 14, margin: '0 0 8px' }}>{title}</h3>
        <p className="stat-value" style={{ fontSize: 32, fontWeight: 700, margin: '0 0 2px' }}>
          {loading ? '—' : count}
        </p>
        <p className="kpi-label muted">{unit}</p>
        <p className="muted" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.4 }}>{description}</p>
        <p style={{ fontSize: 11, color, marginTop: 8 }}>詳細を確認 →</p>
      </article>
    </Link>
  )
}

export function CleanupSummaryPanel() {
  const blurry = useQuery({ queryKey: ['blurry', 80], queryFn: () => api.blurry(80) })
  const duplicates = useQuery({ queryKey: ['duplicates', false], queryFn: () => api.duplicates(false) })
  const similar = useQuery({ queryKey: ['similar', 5], queryFn: () => api.similar(5) })
  const tiny = useQuery({ queryKey: ['tiny', 50 * 1024], queryFn: () => api.tinyFiles(50 * 1024) })

  const isLoading = blurry.isPending || duplicates.isPending || similar.isPending || tiny.isPending
  const isError = blurry.isError || duplicates.isError || similar.isError || tiny.isError

  const dupFiles = (duplicates.data?.groups ?? []).reduce((s, g) => s + g.count, 0)
  const simFiles = (similar.data?.groups ?? []).reduce((s, g) => s + g.count, 0)

  return (
    <section className="dashboard-section">
      <h3 className="section-title">Clean Up Summary</h3>
      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={blurry.error ?? duplicates.error ?? similar.error ?? tiny.error}
        isEmpty={false}
        loadingMessage="集計情報を読み込み中..."
      />
      {!isError && (
        <div className="card-grid card-grid--tiles">
          <SummaryCard
            title="Duplicates"
            count={duplicates.data?.groups.length ?? 0}
            unit={`groups (${dupFiles} files)`}
            description="MD5ハッシュが同一の完全重複ファイル。"
            to="/duplicates"
            color="#f87171"
            loading={duplicates.isPending}
          />
          <SummaryCard
            title="Blurry Photos"
            count={blurry.data?.items.length ?? 0}
            unit="items (閾値80以下)"
            description="ブレ・ピンボケ検出。スコアが低いほどぼけています。"
            to="/blurry"
            color="#fb923c"
            loading={blurry.isPending}
          />
          <SummaryCard
            title="Similar Groups"
            count={similar.data?.groups.length ?? 0}
            unit={`groups (${simFiles} files)`}
            description="見た目が近い連写・類似画像。"
            to="/similar"
            color="#a78bfa"
            loading={similar.isPending}
          />
          <SummaryCard
            title="Tiny Files"
            count={tiny.data?.items.length ?? 0}
            unit="items (50KB以下)"
            description="極小ファイル。不要な低解像度画像を検出します。"
            to="/tiny"
            color="#34d399"
            loading={tiny.isPending}
          />
        </div>
      )}
    </section>
  )
}

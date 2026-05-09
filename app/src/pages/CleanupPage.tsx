import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'

type SummaryCardProps = {
  title: string
  count: number
  unit: string
  description: string
  to: string
  color: string
}

function SummaryCard({ title, count, unit, description, to, color }: SummaryCardProps) {
  return (
    <Link to={to} style={{ textDecoration: 'none' }}>
      <article className="card cleanup-summary-card" style={{ borderTop: `3px solid ${color}` }}>
        <h3 style={{ color }}>{title}</h3>
        <p className="stat-value" style={{ fontSize: 36, fontWeight: 700, margin: '8px 0 4px' }}>{count}</p>
        <p className="kpi-label muted">{unit}</p>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>{description}</p>
        <p style={{ fontSize: 12, color, marginTop: 8 }}>詳細を確認 →</p>
      </article>
    </Link>
  )
}

export function CleanupPage() {
  const blurry = useQuery({ queryKey: ['blurry', 20], queryFn: () => api.blurry(20) })
  const duplicates = useQuery({ queryKey: ['duplicates', false], queryFn: () => api.duplicates(false) })
  const similar = useQuery({ queryKey: ['similar', 5], queryFn: () => api.similar(5) })
  const tiny = useQuery({ queryKey: ['tiny', 50 * 1024], queryFn: () => api.tinyFiles(50 * 1024) })
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats })

  const isLoading = blurry.isPending || duplicates.isPending || similar.isPending || tiny.isPending
  const isError = blurry.isError || duplicates.isError || similar.isError || tiny.isError

  const dupFiles = (duplicates.data?.groups ?? []).reduce((s, g) => s + g.count, 0)
  const simFiles = (similar.data?.groups ?? []).reduce((s, g) => s + g.count, 0)

  return (
    <section className="page">
      <header className="page-header">
        <h2>Clean Up Summary</h2>
        <p className="page-subtitle">整理できるファイルの概要です。各カードをクリックして詳細操作へ進めます。</p>
      </header>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={blurry.error ?? duplicates.error ?? similar.error ?? tiny.error}
        isEmpty={false}
        loadingMessage="集計情報を読み込み中..."
      />

      {!isLoading && !isError && (
        <>
          <div className="card-grid">
            <SummaryCard
              title="Duplicates"
              count={duplicates.data?.groups.length ?? 0}
              unit={`groups (${dupFiles} files)`}
              description="MD5ハッシュが同一の完全重複ファイル。グループ内で1つ残して削除できます。"
              to="/duplicates"
              color="#f87171"
            />
            <SummaryCard
              title="Blurry Photos"
              count={blurry.data?.items.length ?? 0}
              unit="items (閾値20以下)"
              description="ブレ・ピンボケ検出。スコアが低いほどぼけています。"
              to="/blurry"
              color="#fb923c"
            />
            <SummaryCard
              title="Similar Groups"
              count={similar.data?.groups.length ?? 0}
              unit={`groups (${simFiles} files)`}
              description="見た目が近い連写・類似画像。ベストショット以外を一括削除できます。"
              to="/similar"
              color="#a78bfa"
            />
            <SummaryCard
              title="Tiny Files"
              count={tiny.data?.items.length ?? 0}
              unit="items (50KB以下)"
              description="極小ファイル。サムネイルや不要な低解像度画像を検出します。"
              to="/tiny"
              color="#34d399"
            />
          </div>

          <article className="card" style={{ marginTop: 16 }}>
            <h3 className="section-title">ライブラリ全体</h3>
            <div className="card-grid" style={{ marginTop: 12 }}>
              <div className="stat-mini"><span className="muted">総ファイル数</span><strong>{stats.data?.total ?? '-'}</strong></div>
              <div className="stat-mini"><span className="muted">解析済み</span><strong>{stats.data?.analyzed ?? '-'}</strong></div>
              <div className="stat-mini"><span className="muted">ゴミ箱</span><strong>{stats.data?.trashed ?? '-'}</strong></div>
            </div>
          </article>
        </>
      )}
    </section>
  )
}

import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'

export function CleanupPage() {
  const blurry = useQuery({ queryKey: ['blurry'], queryFn: () => api.blurry(20) })
  const duplicates = useQuery({ queryKey: ['duplicates'], queryFn: () => api.duplicates(false) })
  const similar = useQuery({ queryKey: ['similar'], queryFn: () => api.similar(5) })
  const isLoading = blurry.isPending || duplicates.isPending || similar.isPending
  const isError = blurry.isError || duplicates.isError || similar.isError

  return (
    <section className="page">
      <header className="page-header">
        <h2>Clean Up</h2>
        <p className="page-subtitle">重複・ブレ・類似の検出結果をカテゴリごとに確認できます。</p>
      </header>
      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={blurry.error ?? duplicates.error ?? similar.error}
        isEmpty={false}
        loadingMessage="集計情報を読み込み中..."
      />
      {!isLoading && !isError && <div className="card-grid">
        <article className="card">
          <h3>Duplicates</h3>
          <p className="stat-value">{duplicates.data?.groups.length ?? 0}</p>
          <p className="kpi-label">groups</p>
        </article>
        <article className="card">
          <h3>Blurry</h3>
          <p className="stat-value">{blurry.data?.items.length ?? 0}</p>
          <p className="kpi-label">items</p>
        </article>
        <article className="card">
          <h3>Similar</h3>
          <p className="stat-value">{similar.data?.groups.length ?? 0}</p>
          <p className="kpi-label">groups</p>
        </article>
      </div>}
      <article className="card">
        <p className="muted">
          ここは入口ページです。グループ別の詳細操作（代表ショット選択、一括適用）は次段で追加できます。
        </p>
      </article>
    </section>
  )
}


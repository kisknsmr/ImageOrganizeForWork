import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function CleanupPage() {
  const blurry = useQuery({ queryKey: ['blurry'], queryFn: () => api.blurry(20) })
  const duplicates = useQuery({ queryKey: ['duplicates'], queryFn: api.duplicates })
  const similar = useQuery({ queryKey: ['similar'], queryFn: () => api.similar(5) })

  return (
    <section className="page">
      <h2>Clean Up</h2>
      <div className="card-grid">
        <article className="card">
          <h3>Duplicates</h3>
          <p>{duplicates.data?.groups.length ?? 0} groups</p>
        </article>
        <article className="card">
          <h3>Blurry</h3>
          <p>{blurry.data?.items.length ?? 0} items</p>
        </article>
        <article className="card">
          <h3>Similar</h3>
          <p>{similar.data?.groups.length ?? 0} groups</p>
        </article>
      </div>
      <article className="card">
        <p className="muted">
          ここは入口ページです。グループ別の詳細操作（代表ショット選択、一括適用）は次段で追加できます。
        </p>
      </article>
    </section>
  )
}


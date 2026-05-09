import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'

export function SimilarPage() {
  const similar = useQuery({ queryKey: ['similar', 5], queryFn: () => api.similar(5) })

  return (
    <section className="page">
      <header className="page-header">
        <h2>Similar Groups</h2>
        <p className="page-subtitle">近い特徴量を持つ画像グループを確認し、代表ショット選択に繋げます。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Groups: {similar.data?.groups.length ?? 0}
          </span>
        </div>
      </div>
      <article className="card">
        <QueryState
          isLoading={similar.isPending}
          isError={similar.isError}
          error={similar.error}
          isEmpty={!similar.isPending && !similar.isError && (similar.data?.groups.length ?? 0) === 0}
          loadingMessage="類似グループを読み込み中..."
          emptyMessage="類似グループは見つかりませんでした。"
        />
        <p>類似グループ: {similar.data?.groups.length ?? 0}</p>
      </article>
      <div className="list-grid">
        {!similar.isPending &&
          !similar.isError &&
          (similar.data?.groups ?? []).slice(0, 50).map((group) => (
            <article key={group.id} className="card">
              <h3>Group ({group.count})</h3>
              <p className="mono">best: {group.best_id ?? '-'}</p>
              <p className="muted">group id: {group.id}</p>
            </article>
          ))}
      </div>
    </section>
  )
}


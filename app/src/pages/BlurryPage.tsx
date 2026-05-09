import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { ViewControls } from '../components/ViewControls'
import { useViewMode } from '../hooks/useViewMode'

export function BlurryPage() {
  const view = useViewMode('blurry')
  const blurry = useQuery({ queryKey: ['blurry', 20], queryFn: () => api.blurry(20) })
  const items = (blurry.data?.items ?? []).slice(0, 60)

  return (
    <section className="page">
      <header className="page-header">
        <h2>Blurry Photos</h2>
        <p className="page-subtitle">ぼけスコアが低い画像候補を確認し、削除判断の前段として使います。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Candidates: {blurry.data?.items.length ?? 0}
          </span>
        </div>
        <div className="toolbar-group">
          <ViewControls
            mode={view.mode}
            size={view.size}
            sizeMin={view.sizeMin}
            sizeMax={view.sizeMax}
            onModeChange={view.setMode}
            onSizeChange={view.setSize}
          />
        </div>
      </div>
      <article className="card">
        <QueryState
          isLoading={blurry.isPending}
          isError={blurry.isError}
          error={blurry.error}
          isEmpty={!blurry.isPending && !blurry.isError && items.length === 0}
          loadingMessage="ぼけ候補を読み込み中..."
          emptyMessage="ぼけ候補は見つかりませんでした。"
        />
        <p>ぼけ候補: {blurry.data?.items.length ?? 0} 件</p>
      </article>
      <div
        className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
        style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
      >
        {!blurry.isPending &&
          !blurry.isError &&
          items.map((item) => (
            <button key={item.id} className="thumb-item">
              <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
              <span>{item.filename}</span>
              <p className="thumb-meta">blur: {item.blur_score ?? '-'}</p>
            </button>
          ))}
      </div>
    </section>
  )
}

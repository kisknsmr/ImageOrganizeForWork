import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'

export function CleanupPage() {
  // しきい値はサーバーの既定値に追従させる（各詳細ページと同じ値で数えるため）
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const blurThreshold = settings.data?.defaults.blur_threshold ?? 20
  const similarDistance = settings.data?.defaults.similarity_threshold ?? 5

  // queryKey は各詳細ページと揃える。別キーにすると同じ解析を二重に走らせてしまう
  const blurry = useQuery({
    queryKey: ['blurry', blurThreshold],
    queryFn: () => api.blurry(blurThreshold),
    enabled: settings.isSuccess,
  })
  const duplicates = useQuery({
    queryKey: ['duplicates', false],
    queryFn: () => api.duplicates(false),
  })
  const similar = useQuery({
    queryKey: ['similar', similarDistance],
    queryFn: () => api.similar(similarDistance),
    enabled: settings.isSuccess,
  })

  const isLoading = settings.isPending || blurry.isPending || duplicates.isPending || similar.isPending
  const isError = settings.isError || blurry.isError || duplicates.isError || similar.isError

  const cards = [
    {
      to: '/duplicates',
      title: 'Duplicates',
      value: duplicates.data?.groups.length ?? 0,
      unit: 'groups',
      note: '同一ハッシュ・同一サイズのファイル',
    },
    {
      to: '/blurry',
      title: 'Blurry',
      value: blurry.data?.items.length ?? 0,
      unit: 'items',
      note: `ぼけスコア < ${blurThreshold}`,
    },
    {
      to: '/similar',
      title: 'Similar',
      value: similar.data?.groups.length ?? 0,
      unit: 'groups',
      note: `ハミング距離 ≦ ${similarDistance}`,
    },
    {
      to: '/tiny',
      title: 'Tiny Files',
      value: null,
      unit: '',
      note: '低容量ファイルを一覧して整理',
    },
  ]

  return (
    <section className="page">
      <header className="page-header">
        <h2>Clean Up</h2>
        <p className="page-subtitle">
          重複・ブレ・類似の検出結果をまとめて確認し、カードから各詳細ページへ移動して整理します。
        </p>
      </header>
      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={settings.error ?? blurry.error ?? duplicates.error ?? similar.error}
        isEmpty={false}
        loadingMessage="集計情報を読み込み中..."
      />
      {!isLoading && !isError && (
        <div className="card-grid">
          {cards.map((card) => (
            <Link key={card.to} to={card.to} className="card selectable" style={{ textDecoration: 'none' }}>
              <h3>{card.title}</h3>
              {card.value !== null ? (
                <>
                  <p className="stat-value">{card.value}</p>
                  <p className="kpi-label">{card.unit}</p>
                </>
              ) : (
                <p className="stat-value">→</p>
              )}
              <p className="muted">{card.note}</p>
            </Link>
          ))}
        </div>
      )}
      {!isLoading && !isError && (blurry.data?.truncated || similar.data?.truncated) && (
        <article className="card">
          <p className="muted analyze-note">
            一部の集計は上限で打ち切られています（
            {blurry.data?.truncated ? `ぼけ候補 ${blurry.data.available} 件中 ${blurry.data.limit} 件` : ''}
            {blurry.data?.truncated && similar.data?.truncated ? ' / ' : ''}
            {similar.data?.truncated ? `類似判定 ${similar.data.available} 件中 ${similar.data.scanned} 件` : ''}
            ）。実際の件数はこれより多い可能性があります。
          </p>
        </article>
      )}
    </section>
  )
}

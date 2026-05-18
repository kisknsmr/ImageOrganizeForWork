import { ThumbnailImg } from '../components/ThumbnailImg'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memo, useCallback, useMemo, useState } from 'react'
import { api } from '../api/client'
import { FileDetailPane } from '../components/FileDetailPane'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useViewMode } from '../hooks/useViewMode'
import type { FileItem } from '../types'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

type CardProps = {
  item: FileItem
  isBest: boolean
  selected: boolean
  previewing: boolean
  busy: boolean
  onToggle: (id: number) => void
  onPreview: (item: FileItem) => void
  onDragStart: (id: number) => (e: React.DragEvent<HTMLElement>) => void
}

const SimilarCard = memo(function SimilarCard({
  item, isBest, selected, previewing, busy, onToggle, onPreview, onDragStart,
}: CardProps) {
  return (
    <label
      className={`thumb-item checkbox-card ${isBest ? 'best-shot' : ''} ${selected ? 'selected' : ''} ${previewing ? 'previewing' : ''}`}
      draggable
      onDragStart={onDragStart(item.id)}
      onClick={() => onPreview(item)}
      title={isBest ? 'ベストショット' : ''}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(item.id)}
        disabled={busy}
        onClick={(e) => e.stopPropagation()}
      />
      <ThumbnailImg src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
      {isBest && <span className="best-badge">★</span>}
      <span>{item.filename}</span>
      <p className="thumb-meta">
        {item.blur_score != null ? `blur: ${item.blur_score.toFixed(1)}` : item.extension}
        {' · '}{formatBytes(item.size)}
      </p>
    </label>
  )
})

export function SimilarPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const view = useViewMode('similar')
  const [distance, setDistance] = useState(5)
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)

  const similar = useQuery({
    queryKey: ['similar', distance],
    queryFn: () => api.similar(distance),
  })

  const currentGroup = useMemo(
    () => similar.data?.groups.find((g) => g.id === selectedGroupId) ?? null,
    [similar.data, selectedGroupId],
  )

  const toggle = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const handlePreview = useCallback((item: FileItem) => {
    setPreviewItem(item)
  }, [])

  const selectAllExceptBest = useCallback(() => {
    if (!currentGroup) return
    setSelectedIds(new Set(currentGroup.items.filter((i) => i.id !== currentGroup.best_id).map((i) => i.id)))
  }, [currentGroup])

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`ゴミ箱移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Similar')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ送りました`, 'Similar')
      }
      setSelectedIds(new Set())
      setSelectedGroupId(null)
      setPreviewItem(null)
      await similar.refetch()
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱移動に失敗しました')
    },
  })

  const selectedArray = useMemo(() => Array.from(selectedIds), [selectedIds])
  const onDragStart = useDraggableFiles(selectedArray)
  const busy = trashMutation.isPending
  const groups = similar.data?.groups ?? []

  return (
    <section className="page">
      <header className="page-header">
        <h2>Similar Groups</h2>
        <p className="page-subtitle">見た目が近い画像をグループ化します。ベストショットを残して他をゴミ箱へ送れます。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {similar.isPending ? '読込中...' : `Groups: ${groups.length}`}
          </span>
          {currentGroup && <span className="muted">Selected: {selectedIds.size} / {currentGroup.items.length}</span>}
        </div>
        <div className="toolbar-group">
          <label className="row" style={{ gap: 8, alignItems: 'center' }}>
            <span className="muted" style={{ whiteSpace: 'nowrap' }}>類似度: {distance}</span>
            <input
              type="range" min={1} max={25} value={distance}
              onChange={(e) => { setDistance(Number(e.target.value)); setSelectedGroupId(null); setSelectedIds(new Set()) }}
              style={{ width: 120 }}
            />
          </label>
          <ViewControls
            mode={view.mode} size={view.size} sizeMin={view.sizeMin} sizeMax={view.sizeMax}
            onModeChange={view.setMode} onSizeChange={view.setSize}
          />
          <button className="button ghost" disabled={busy || !currentGroup} onClick={selectAllExceptBest}>
            ベスト以外を選択
          </button>
          <button
            className="button danger"
            disabled={busy || selectedIds.size === 0}
            onClick={() => trashMutation.mutate(selectedArray)}
          >
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            選択をゴミ箱へ ({selectedIds.size})
          </button>
        </div>
      </div>

      {/* 3ペインレイアウト: グループ一覧 | サムネイル一覧 | プレビュー詳細 */}
      <div className="gallery-layout" style={{ gridTemplateColumns: 'minmax(220px, 24vw) 1fr 300px' }}>
        {/* 左: グループ一覧 */}
        <div className="pane-scroll">
          <p className="pane-heading muted">グループ一覧</p>
          <QueryState
            isLoading={similar.isPending} isError={similar.isError} error={similar.error}
            isEmpty={!similar.isPending && !similar.isError && groups.length === 0}
            loadingMessage="類似グループを分析中..."
            emptyMessage="類似グループは見つかりませんでした。類似度を上げてみてください。"
          />
          <div className="group-picker-list">
            {!similar.isPending && !similar.isError && groups.map((group) => (
              <button
                key={group.id}
                className={`group-picker-item card selectable ${selectedGroupId === group.id ? 'selected' : ''}`}
                onClick={() => { setSelectedGroupId(group.id); setSelectedIds(new Set()); setPreviewItem(null) }}
              >
                {group.best_id && (
                  <img
                    src={api.thumbnailUrl(group.best_id)}
                    alt="best"
                    className="group-picker-thumb"
                    loading="lazy"
                  />
                )}
                <div className="group-picker-info">
                  <p style={{ margin: 0, fontWeight: 600, fontSize: 13 }}>{group.count} 枚</p>
                  <p className="muted" style={{ fontSize: 11, margin: 0 }}>#{group.id.slice(0, 8)}</p>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 中央: グループ内サムネイル */}
        <aside className="preview-pane pane-scroll">
          {!currentGroup && <p className="muted">左からグループを選択してください。</p>}
          {currentGroup && (
            <>
              <p className="muted" style={{ marginBottom: 8, fontSize: 12 }}>★ = ベストショット（ぼけスコア・サイズ上位）</p>
              <div
                className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
                style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
              >
                {currentGroup.items.map((item) => (
                  <SimilarCard
                    key={item.id}
                    item={item}
                    isBest={item.id === currentGroup.best_id}
                    selected={selectedIds.has(item.id)}
                    previewing={previewItem?.id === item.id}
                    busy={busy}
                    onToggle={toggle}
                    onPreview={handlePreview}
                    onDragStart={onDragStart}
                  />
                ))}
              </div>
            </>
          )}
        </aside>

        {/* 右: プレビュー＋詳細 */}
        <div className="pane-scroll">
          <FileDetailPane item={previewItem} placeholder="サムネイルをクリックしてプレビュー" />
        </div>
      </div>
    </section>
  )
}

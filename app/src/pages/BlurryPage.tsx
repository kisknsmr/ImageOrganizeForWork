import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { FileDetailPane } from '../components/FileDetailPane'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useViewMode } from '../hooks/useViewMode'
import type { FileItem } from '../types'

export function BlurryPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const view = useViewMode('blurry')
  const [threshold, setThreshold] = useState(20)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)

  const blurry = useQuery({
    queryKey: ['blurry', threshold],
    queryFn: () => api.blurry(threshold),
  })
  const items = blurry.data?.items ?? []

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const toggleAll = () => {
    setSelectedIds(selectedIds.length === items.length ? [] : items.map((i) => i.id))
  }

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`ゴミ箱移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Blurry')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ送りました`, 'Blurry')
      }
      setSelectedIds([])
      setPreviewItem(null)
      await blurry.refetch()
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱移動に失敗しました')
    },
  })

  const onDragStart = useDraggableFiles(selectedIds)
  const busy = trashMutation.isPending
  const allSelected = items.length > 0 && selectedIds.length === items.length

  return (
    <section className="page">
      <header className="page-header">
        <h2>Blurry Photos</h2>
        <p className="page-subtitle">ぼけスコアが低い画像を確認してゴミ箱へ送ります。スコアが低いほどぼけています。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Candidates: {items.length}
          </span>
          <span className="muted">Selected: {selectedIds.length}</span>
        </div>
        <div className="toolbar-group">
          <label className="row" style={{ gap: 8, alignItems: 'center' }}>
            <span className="muted" style={{ whiteSpace: 'nowrap' }}>閾値: {threshold}</span>
            <input
              type="range" min={5} max={100} value={threshold}
              onChange={(e) => { setThreshold(Number(e.target.value)); setSelectedIds([]) }}
              style={{ width: 120 }}
            />
          </label>
          <ViewControls
            mode={view.mode} size={view.size} sizeMin={view.sizeMin} sizeMax={view.sizeMax}
            onModeChange={view.setMode} onSizeChange={view.setSize}
          />
          <button className="button ghost" onClick={toggleAll} disabled={busy || items.length === 0}>
            {allSelected ? '全解除' : '全選択'}
          </button>
          <button
            className="button danger"
            disabled={busy || selectedIds.length === 0}
            onClick={() => trashMutation.mutate(selectedIds)}
          >
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            選択をゴミ箱へ ({selectedIds.length})
          </button>
        </div>
      </div>
      <QueryState
        isLoading={blurry.isPending} isError={blurry.isError} error={blurry.error}
        isEmpty={!blurry.isPending && !blurry.isError && items.length === 0}
        loadingMessage="ぼけ候補を読み込み中..."
        emptyMessage="ぼけ候補は見つかりませんでした。閾値を上げてみてください。"
      />
      <div className="gallery-layout with-folder">
        <div
          className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
          style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
        >
          {!blurry.isPending && !blurry.isError && items.map((item) => (
            <label
              key={item.id}
              className={`thumb-item checkbox-card ${selectedIds.includes(item.id) ? 'selected' : ''} ${previewItem?.id === item.id ? 'previewing' : ''}`}
              draggable
              onDragStart={onDragStart(item.id)}
              onClick={() => setPreviewItem(item)}
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(item.id)}
                onChange={() => toggle(item.id)}
                disabled={busy}
                onClick={(e) => e.stopPropagation()}
              />
              <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
              <span>{item.filename}</span>
              <p className="thumb-meta">blur: {item.blur_score?.toFixed(1) ?? '-'}</p>
            </label>
          ))}
        </div>
        <FileDetailPane item={previewItem} placeholder="サムネイルをクリックしてプレビュー" />
      </div>
    </section>
  )
}

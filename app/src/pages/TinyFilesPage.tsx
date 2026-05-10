import { ThumbnailImg } from '../components/ThumbnailImg'
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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const PRESETS = [
  { label: '10 KB', value: 10 * 1024 },
  { label: '50 KB', value: 50 * 1024 },
  { label: '100 KB', value: 100 * 1024 },
  { label: '500 KB', value: 500 * 1024 },
  { label: '1 MB', value: 1024 * 1024 },
]

export function TinyFilesPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const view = useViewMode('tiny')
  const [maxSize, setMaxSize] = useState(50 * 1024)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)

  const tiny = useQuery({
    queryKey: ['tiny', maxSize],
    queryFn: () => api.tinyFiles(maxSize),
  })
  const items = tiny.data?.items ?? []

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
        toast.warning(`ゴミ箱移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Tiny Files')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ送りました`, 'Tiny Files')
      }
      setSelectedIds([])
      setPreviewItem(null)
      await tiny.refetch()
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
        <h2>Tiny Files</h2>
        <p className="page-subtitle">指定サイズ以下の極小ファイルを検出してゴミ箱へ送ります。</p>
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
          <span className="muted" style={{ whiteSpace: 'nowrap' }}>上限サイズ:</span>
          {PRESETS.map((p) => (
            <button
              key={p.value}
              className={`button ${maxSize === p.value ? '' : 'ghost'}`}
              onClick={() => { setMaxSize(p.value); setSelectedIds([]) }}
              disabled={busy}
            >
              {p.label}
            </button>
          ))}
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
        isLoading={tiny.isPending} isError={tiny.isError} error={tiny.error}
        isEmpty={!tiny.isPending && !tiny.isError && items.length === 0}
        loadingMessage="極小ファイルを検索中..."
        emptyMessage={`${formatBytes(maxSize)} 以下のファイルは見つかりませんでした。`}
      />
      <div className="gallery-layout with-folder">
        <div className="pane-scroll">
        <div
          className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
          style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
        >
          {!tiny.isPending && !tiny.isError && items.map((item) => (
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
              <ThumbnailImg src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
              <span>{item.filename}</span>
              <p className="thumb-meta">{formatBytes(item.size)}</p>
            </label>
          ))}
        </div>
        </div>
        <div className="pane-scroll">
          <FileDetailPane item={previewItem} placeholder="サムネイルをクリックしてプレビュー" />
        </div>
      </div>
    </section>
  )
}

import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useViewMode } from '../hooks/useViewMode'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

export function TinyFilesPage() {
  const toast = useToast()
  const view = useViewMode('tiny')
  const [maxSizeKb, setMaxSizeKb] = useState(10)
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  const tiny = useQuery({
    queryKey: ['tiny', maxSizeKb],
    queryFn: () => api.tiny(maxSizeKb),
  })
  const items = tiny.data?.items ?? []

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const selectAll = () => setSelectedIds(items.map((item) => item.id))
  const clearSelection = () => setSelectedIds([])

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`ゴミ箱へ: ${res.moved} 件 / 失敗: ${failed} 件`, 'Tiny Files')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ移動しました`, 'Tiny Files')
      }
      setSelectedIds([])
      await tiny.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱への移動に失敗しました')
    },
  })

  const trashSelected = () => {
    if (!selectedIds.length) return
    if (!window.confirm(`${selectedIds.length} 件をゴミ箱へ移動しますか？`)) return
    trashMutation.mutate(selectedIds)
  }

  const busy = trashMutation.isPending

  return (
    <section className="page">
      <header className="page-header">
        <h2>Tiny Files</h2>
        <p className="page-subtitle">指定サイズ未満の低容量ファイルを抽出し、まとめてゴミ箱へ移動できます。</p>
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
        <div className="row">
          <label className="muted">
            最小しきい値:
            <input
              className="input"
              type="number"
              min={1}
              max={100000}
              value={maxSizeKb}
              onChange={(e) => setMaxSizeKb(Math.max(1, Number(e.target.value) || 1))}
              disabled={busy}
              style={{ width: 100, marginLeft: 8 }}
            />
            <span style={{ marginLeft: 4 }}>KB 未満</span>
          </label>
          <button className="button secondary" disabled={busy || !items.length} onClick={selectAll}>
            すべて選択
          </button>
          <button className="button secondary" disabled={busy || !selectedIds.length} onClick={clearSelection}>
            選択解除
          </button>
          <button className="button danger" disabled={busy || !selectedIds.length} onClick={trashSelected}>
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            ゴミ箱へ ({selectedIds.length})
          </button>
        </div>
        <QueryState
          isLoading={tiny.isPending}
          isError={tiny.isError}
          error={tiny.error}
          isEmpty={!tiny.isPending && !tiny.isError && items.length === 0}
          loadingMessage="低容量ファイルを検索中..."
          emptyMessage="該当するファイルは見つかりませんでした。"
        />
      </article>
      <div
        className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
        style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
      >
        {!tiny.isPending &&
          !tiny.isError &&
          items.map((item) => (
            <label key={item.id} className="thumb-item checkbox-card">
              <input
                type="checkbox"
                checked={selectedIds.includes(item.id)}
                onChange={() => toggle(item.id)}
                disabled={busy}
              />
              <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
              <span>{item.filename}</span>
              <p className="thumb-meta">{formatSize(item.size)}</p>
            </label>
          ))}
      </div>
    </section>
  )
}

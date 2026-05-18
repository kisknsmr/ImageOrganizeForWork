import { ThumbnailImg } from '../components/ThumbnailImg'
import { useMutation, useQuery } from '@tanstack/react-query'
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

type CardProps = {
  item: FileItem
  selected: boolean
  previewing: boolean
  busy: boolean
  onToggle: (id: number) => void
  onPreview: (item: FileItem) => void
  onDragStart: (id: number) => (e: React.DragEvent<HTMLElement>) => void
}

const DuplicateCard = memo(function DuplicateCard({
  item, selected, previewing, busy, onToggle, onPreview, onDragStart,
}: CardProps) {
  return (
    <label
      className={`thumb-item checkbox-card ${selected ? 'selected' : ''} ${previewing ? 'previewing' : ''}`}
      draggable
      onDragStart={onDragStart(item.id)}
      onClick={() => onPreview(item)}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(item.id)}
        disabled={busy}
        onClick={(e) => e.stopPropagation()}
      />
      <ThumbnailImg src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
      <span>{item.filename}</span>
    </label>
  )
})

export function DuplicatesPage() {
  const toast = useToast()
  const view = useViewMode('duplicates')
  const [useFullHash, setUseFullHash] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)

  const duplicates = useQuery({
    queryKey: ['duplicates', useFullHash],
    queryFn: () => api.duplicates(useFullHash),
  })

  const currentGroup = useMemo(
    () => duplicates.data?.groups.find((g) => g.hash === selectedGroup) ?? null,
    [duplicates.data, selectedGroup],
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

  const selectAllExceptFirst = useCallback(() => {
    if (!currentGroup) return
    setSelectedIds(new Set(currentGroup.items.slice(1).map((i) => i.id)))
  }, [currentGroup])

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Duplicates')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ送りました`, 'Duplicates')
      }
      setSelectedIds(new Set())
      setPreviewItem(null)
      await duplicates.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱移動に失敗しました')
    },
  })

  const fullHashMutation = useMutation({
    mutationFn: () => api.analyzeFullHashStart(),
    onSuccess: async (res) => {
      if (!res.started) {
        toast.info(res.message ?? '対象がありません', 'Duplicates')
        return
      }
      toast.success('ファイル全体の MD5 計算を開始しました。ジョブ完了後に再読み込みしてください。', 'Duplicates')
      await duplicates.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '完全ハッシュの開始に失敗しました')
    },
  })

  const selectedArray = useMemo(() => Array.from(selectedIds), [selectedIds])
  const onDragStart = useDraggableFiles(selectedArray)
  const busy = trashMutation.isPending

  return (
    <section className="page">
      <header className="page-header">
        <h2>Duplicates</h2>
        <p className="page-subtitle">同一ハッシュの画像グループを確認し、不要ファイルをゴミ箱へ送ります。</p>
      </header>

      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {duplicates.isPending ? '読込中...' : `${duplicates.data?.groups.length ?? 0} groups`}
          </span>
          {currentGroup && (
            <span className="muted">Selected: {selectedIds.size} / {currentGroup.items.length}</span>
          )}
        </div>
        <div className="toolbar-group">
          <ViewControls
            mode={view.mode} size={view.size} sizeMin={view.sizeMin} sizeMax={view.sizeMax}
            onModeChange={view.setMode} onSizeChange={view.setSize}
          />
          <button className={`button ${!useFullHash ? '' : 'secondary'}`} onClick={() => setUseFullHash(false)}>
            簡易 (高速)
          </button>
          <button className={`button ${useFullHash ? '' : 'secondary'}`} onClick={() => setUseFullHash(true)}>
            完全 (精密)
          </button>
          <button
            type="button" className="button secondary"
            disabled={fullHashMutation.isPending}
            onClick={() => fullHashMutation.mutate()}
          >
            {fullHashMutation.isPending ? <Spinner size={14} inline /> : null}
            完全MD5を計算
          </button>
          <button
            className="button ghost"
            disabled={busy || !currentGroup}
            onClick={selectAllExceptFirst}
          >
            1枚目以外を選択
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

      <div className="gallery-layout" style={{ gridTemplateColumns: 'minmax(220px, 24vw) 1fr 300px' }}>
        {/* 左: グループ一覧 */}
        <div className="pane-scroll">
          <p className="pane-heading muted">グループ一覧</p>
          <QueryState
            isLoading={duplicates.isPending} isError={duplicates.isError} error={duplicates.error}
            isEmpty={!duplicates.isPending && !duplicates.isError && (duplicates.data?.groups.length ?? 0) === 0}
            loadingMessage="重複グループを分析中..."
            emptyMessage="重複グループは見つかりませんでした。"
          />
          {!duplicates.isPending && !duplicates.isError && (
            <div className="group-picker-list">
              {(duplicates.data?.groups ?? []).map((group) => (
                <button
                  key={group.hash}
                  className={`group-picker-item card selectable ${selectedGroup === group.hash ? 'selected' : ''}`}
                  onClick={() => { setSelectedGroup(group.hash); setSelectedIds(new Set()); setPreviewItem(null) }}
                >
                  {group.items[0] && (
                    <img
                      src={api.thumbnailUrl(group.items[0].id)}
                      alt="dup"
                      className="group-picker-thumb"
                      loading="lazy"
                    />
                  )}
                  <div className="group-picker-info">
                    <p style={{ margin: 0, fontWeight: 600, fontSize: 13 }}>{group.count} files</p>
                    <p className="muted" style={{ fontSize: 11, margin: 0 }}>{group.hash.slice(0, 10)}…</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 中央: グループ内サムネイル */}
        <aside className="preview-pane pane-scroll">
          {!currentGroup && (
            <p className="muted" style={{ padding: 16 }}>左からグループを選択してください。</p>
          )}
          {currentGroup && (
            <div
              className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
              style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
            >
              {currentGroup.items.map((item) => (
                <DuplicateCard
                  key={item.id}
                  item={item}
                  selected={selectedIds.has(item.id)}
                  previewing={previewItem?.id === item.id}
                  busy={busy}
                  onToggle={toggle}
                  onPreview={handlePreview}
                  onDragStart={onDragStart}
                />
              ))}
            </div>
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

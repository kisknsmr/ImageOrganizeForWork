import { ThumbnailImg } from '../components/ThumbnailImg'
import { useMutation, useQuery } from '@tanstack/react-query'
import { memo, useCallback, useMemo, useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
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
  busy: boolean
  onToggle: (id: number) => void
  onDragStart: (id: number) => (e: React.DragEvent<HTMLElement>) => void
}

const ManualSortCard = memo(function ManualSortCard({
  item, selected, busy, onToggle, onDragStart,
}: CardProps) {
  return (
    <label
      className="thumb-item checkbox-card"
      draggable
      onDragStart={onDragStart(item.id)}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(item.id)}
        disabled={busy}
      />
      <ThumbnailImg src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
      <span>{item.filename}</span>
      <p className="thumb-meta">{item.content_type ?? item.extension}</p>
    </label>
  )
})

export function ManualSortPage() {
  const toast = useToast()
  const view = useViewMode('manual-sort')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [destinationFolder, setDestinationFolder] = useState('')

  const files = useQuery({
    queryKey: ['manual-files'],
    queryFn: () => api.files(new URLSearchParams({ page: '1', limit: '100' })),
  })
  const folders = useQuery({ queryKey: ['folders'], queryFn: api.folders })

  const toggle = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const moveMutation = useMutation({
    mutationFn: ({ ids, folder }: { ids: number[]; folder: string }) => api.batchMoveFile(ids, folder),
    onSuccess: async (res, vars) => {
      const failed = res.failed_ids?.length ?? 0
      const folderLabel = vars.folder.split(/[\\/]/).pop() || vars.folder
      if (failed > 0) {
        toast.warning(`${folderLabel} へ移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Manual Sort')
      } else {
        toast.success(`${res.moved} 件を「${folderLabel}」へ移動しました`, 'Manual Sort')
      }
      setSelectedIds(new Set())
      await files.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '移動に失敗しました')
    },
  })

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`ゴミ箱移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Manual Sort')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ送りました`, 'Manual Sort')
      }
      setSelectedIds(new Set())
      await files.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱移動に失敗しました')
    },
  })

  const handleDropToFolder = (folder: string, ids: number[]) => {
    moveMutation.mutate({ ids, folder })
  }

  const handleFolderCreated = (path: string) => {
    folders.refetch()
    setDestinationFolder(path)
  }

  const selectedArray = useMemo(() => Array.from(selectedIds), [selectedIds])
  const onDragStart = useDraggableFiles(selectedArray)
  const busy = moveMutation.isPending || trashMutation.isPending
  const items = (files.data?.items ?? []).slice(0, 60)

  return (
    <section className="page">
      <header className="page-header">
        <h2>Manual Sort</h2>
        <p className="page-subtitle">選択した画像を任意フォルダへ移動、またはゴミ箱へまとめて送れます。サムネをドラッグでフォルダへ直接移動できます。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Files: {files.data?.total ?? 0}
          </span>
          <span className="muted">Selected: {selectedIds.size}</span>
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
          isLoading={files.isPending || folders.isPending}
          isError={files.isError || folders.isError}
          error={files.error ?? folders.error}
          isEmpty={false}
          loadingMessage="ファイルとフォルダ情報を読み込み中..."
        />
        <p>対象ファイル: {files.data?.total ?? 0}</p>
        <div className="row">
          <select
            className="input"
            value={destinationFolder}
            onChange={(e) => setDestinationFolder(e.target.value)}
            disabled={busy}
          >
            <option value="">移動先フォルダを選択</option>
            {(folders.data?.folders ?? []).map((folder) => (
              <option key={folder} value={folder}>
                {folder}
              </option>
            ))}
          </select>
          <button
            className="button"
            disabled={busy || !selectedIds.size || !destinationFolder}
            onClick={() => moveMutation.mutate({ ids: selectedArray, folder: destinationFolder })}
          >
            {moveMutation.isPending ? <Spinner size={14} inline /> : null}
            選択を移動 ({selectedIds.size})
          </button>
          <button
            className="button danger"
            disabled={busy || !selectedIds.size}
            onClick={() => trashMutation.mutate(selectedArray)}
          >
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            選択をゴミ箱へ
          </button>
        </div>
      </article>
      <div className="gallery-layout with-folder">
        <div className="pane-scroll">
          <div
            className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
            style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
          >
            {!files.isPending &&
              !files.isError &&
              items.map((item) => (
                <ManualSortCard
                  key={item.id}
                  item={item}
                  selected={selectedIds.has(item.id)}
                  busy={busy}
                  onToggle={toggle}
                  onDragStart={onDragStart}
                />
              ))}
          </div>
        </div>
        <FolderDropPanel
          folders={folders.data?.folders ?? []}
          onDropFiles={handleDropToFolder}
          onFolderCreated={handleFolderCreated}
          disabled={busy}
        />
      </div>
    </section>
  )
}

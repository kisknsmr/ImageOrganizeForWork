import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
import { PaneResizer } from '../components/PaneResizer'
import { PreviewPane } from '../components/PreviewPane'
import { QueryState } from '../components/QueryState'
import { ResizableLayout } from '../components/ResizableLayout'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useResizablePane } from '../hooks/useResizablePane'
import { useViewMode } from '../hooks/useViewMode'
import type { FileItem } from '../types'

const PAGE_SIZE = 60

export function ManualSortPage() {
  const toast = useToast()
  const view = useViewMode('manual-sort')
  const pane = useResizablePane('manual-sort')
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [destinationFolder, setDestinationFolder] = useState('')
  const [page, setPage] = useState(1)

  const files = useQuery({
    queryKey: ['manual-files', page],
    queryFn: () => api.files(new URLSearchParams({ page: String(page), limit: String(PAGE_SIZE) })),
    placeholderData: (prev) => prev,
  })
  const folders = useQuery({ queryKey: ['folders'], queryFn: api.folders })

  const total = files.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  /**
   * 移動・ゴミ箱送りの後に一覧を取り直す。
   * 件数が減って現在のページが範囲外になった場合は最終ページへ押し戻す
   * （でないと空のページが表示されたまま操作できなくなる）。
   */
  const refetchAndClampPage = async () => {
    const { data } = await files.refetch()
    const newTotalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE))
    setPage((p) => Math.min(p, newTotalPages))
  }

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

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
      setSelectedIds([])
      await refetchAndClampPage()
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
      setSelectedIds([])
      await refetchAndClampPage()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱移動に失敗しました')
    },
  })

  const moveSelected = () => {
    if (!selectedIds.length || !destinationFolder) return
    moveMutation.mutate({ ids: selectedIds, folder: destinationFolder })
  }

  const trashSelected = () => {
    if (!selectedIds.length) return
    trashMutation.mutate(selectedIds)
  }

  const handleDropToFolder = (folder: string, ids: number[]) => {
    moveMutation.mutate({ ids, folder })
  }

  const handleFolderCreated = (path: string) => {
    folders.refetch()
    setDestinationFolder(path)
  }

  const onDragStart = useDraggableFiles(selectedIds)
  const busy = moveMutation.isPending || trashMutation.isPending
  const items = files.data?.items ?? []
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const rangeEnd = (page - 1) * PAGE_SIZE + items.length

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
            {rangeStart}-{rangeEnd} / {total}
          </span>
          <span className="muted">Page {page} / {totalPages}</span>
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
          <button
            className="button secondary"
            disabled={busy || page <= 1}
            onClick={() => {
              setPage((p) => Math.max(1, p - 1))
              setSelectedIds([])
            }}
          >
            Prev
          </button>
          <button
            className="button secondary"
            disabled={busy || page >= totalPages}
            onClick={() => {
              setPage((p) => Math.min(totalPages, p + 1))
              setSelectedIds([])
            }}
          >
            Next
          </button>
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
        <p>
          対象ファイル: {total} 件（このページに {items.length} 件を表示）
        </p>
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
            disabled={busy || !selectedIds.length || !destinationFolder}
            onClick={moveSelected}
          >
            {moveMutation.isPending ? <Spinner size={14} inline /> : null}
            選択を移動 ({selectedIds.length})
          </button>
          <button
            className="button danger"
            disabled={busy || !selectedIds.length}
            onClick={trashSelected}
          >
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            選択をゴミ箱へ
          </button>
        </div>
      </article>
      <ResizableLayout className="gallery-layout with-folder" pane={pane}>
        <div
          className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
          style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
        >
          {!files.isPending &&
            !files.isError &&
            items.map((item) => (
              <label
                key={item.id}
                className="thumb-item checkbox-card"
                onClick={() => setPreviewItem(item)}
                draggable
                onDragStart={onDragStart(item.id)}
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(item.id)}
                  onChange={() => toggle(item.id)}
                  disabled={busy}
                />
                <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
                <span>{item.filename}</span>
                <p className="thumb-meta">{item.content_type ?? item.extension}</p>
              </label>
            ))}
        </div>
        <PaneResizer
          onPointerDown={pane.onPointerDown}
          onKeyDown={pane.onKeyDown}
          onReset={pane.reset}
          isResizing={pane.isResizing}
        />
        <PreviewPane item={previewItem} emptyMessage="サムネイルをクリックすると、ここに拡大表示と情報が出ます。" />
        <FolderDropPanel
          folders={folders.data?.folders ?? []}
          libraryRoot={folders.data?.root_path}
          counts={folders.data?.counts}
          onDropFiles={handleDropToFolder}
          onFolderCreated={handleFolderCreated}
          disabled={busy}
        />
      </ResizableLayout>
    </section>
  )
}

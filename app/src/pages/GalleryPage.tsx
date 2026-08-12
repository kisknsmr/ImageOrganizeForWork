import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
import { PaneResizer } from '../components/PaneResizer'
import { PageSizeSelect } from '../components/PageSizeSelect'
import { PreviewPane } from '../components/PreviewPane'
import { ResizableLayout } from '../components/ResizableLayout'
import { QueryState } from '../components/QueryState'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { usePageSize } from '../hooks/usePageSize'
import { useResizablePane } from '../hooks/useResizablePane'
import { useViewMode } from '../hooks/useViewMode'
import type { FileItem } from '../types'

export function GalleryPage() {
  const toast = useToast()
  const view = useViewMode('gallery')
  const pane = useResizablePane('gallery')
  const { pageSize, setPageSize } = usePageSize('gallery', 80)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<FileItem | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [showFolderPanel, setShowFolderPanel] = useState(false)
  const params = useMemo(() => {
    const p = new URLSearchParams()
    p.set('page', String(page))
    p.set('limit', String(pageSize))
    return p
  }, [page, pageSize])
  const files = useQuery({ queryKey: ['files', page, pageSize], queryFn: () => api.files(params) })
  const totalPages = Math.max(1, Math.ceil((files.data?.total ?? 0) / pageSize))
  const folders = useQuery({
    queryKey: ['folders'],
    queryFn: api.folders,
    enabled: showFolderPanel,
  })

  const moveMutation = useMutation({
    mutationFn: ({ ids, folder }: { ids: number[]; folder: string }) => api.batchMoveFile(ids, folder),
    onSuccess: async (res, vars) => {
      const failed = res.failed_ids?.length ?? 0
      const folderLabel = vars.folder.split(/[\\/]/).pop() || vars.folder
      if (failed > 0) {
        toast.warning(`${folderLabel} へ移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Gallery')
      } else {
        toast.success(`${res.moved} 件を「${folderLabel}」へ移動しました`, 'Gallery')
      }
      setSelectedIds([])
      await files.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '移動に失敗しました')
    },
  })

  const onDragStart = useDraggableFiles(selectedIds)

  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const handleDrop = (folder: string, ids: number[]) => {
    moveMutation.mutate({ ids, folder })
  }

  const handleFolderCreated = () => {
    folders.refetch()
  }

  const items = files.data?.items ?? []

  return (
    <section className="page">
      <header className="page-header">
        <h2>Gallery</h2>
        <p className="page-subtitle">サムネイルを一覧し、右ペインでプレビューとファイル情報を確認します。Ctrl+クリックで複数選択し、フォルダへドラッグできます。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Loaded {items.length} items
          </span>
          <span className="muted">Page {page} / {totalPages}</span>
          {selectedIds.length > 0 && <span className="muted">Selected: {selectedIds.length}</span>}
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
          <PageSizeSelect
            value={pageSize}
            onChange={(size) => {
              setPageSize(size)
              setPage(1)
            }}
          />
          <button
            className={`button ${showFolderPanel ? '' : 'secondary'}`}
            type="button"
            onClick={() => setShowFolderPanel((v) => !v)}
            title="フォルダパネルでドラッグ＆ドロップ移動"
          >
            {showFolderPanel ? 'パネルを隠す' : 'フォルダパネル'}
          </button>
          <button className="button secondary" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            Prev
          </button>
          <button
            className="button secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </button>
        </div>
      </div>
      <ResizableLayout className={`gallery-layout ${showFolderPanel ? 'with-folder' : ''}`} pane={pane}>
        <div>
          <QueryState
            isLoading={files.isPending}
            isError={files.isError}
            error={files.error}
            isEmpty={!files.isPending && !files.isError && items.length === 0}
            loadingMessage="ギャラリーを読み込み中..."
            emptyMessage="表示できる画像がありません。"
          />
          {!files.isPending && !files.isError && (
            <div
              className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
              style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
            >
              {items.map((item) => {
                const isSelected = selectedIds.includes(item.id)
                return (
                  <button
                    key={item.id}
                    className={`thumb-item ${isSelected ? 'selected' : ''}`}
                    draggable
                    onDragStart={onDragStart(item.id)}
                    onClick={(e) => {
                      if (e.ctrlKey || e.metaKey || e.shiftKey) {
                        toggleSelected(item.id)
                      } else {
                        setSelected(item)
                      }
                    }}
                  >
                    <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
                    <span>{item.filename}</span>
                    <p className="thumb-meta">{item.content_type ?? item.extension}</p>
                  </button>
                )
              })}
            </div>
          )}
        </div>
        <PaneResizer
          onPointerDown={pane.onPointerDown}
          onKeyDown={pane.onKeyDown}
          onReset={pane.reset}
          isResizing={pane.isResizing}
        />
        {/* プレビューは常に出す。フォルダパネルは置き換えではなく列を足す
            （置き換えると、ドラッグ元の画像を確認しながら移動できない） */}
        <PreviewPane item={selected} />
        {showFolderPanel && (
          <FolderDropPanel
            folders={folders.data?.folders ?? []}
            libraryRoot={folders.data?.root_path}
            counts={folders.data?.counts}
            onDropFiles={handleDrop}
            onFolderCreated={handleFolderCreated}
            disabled={moveMutation.isPending}
            title="ドロップで移動"
            hint="サムネをここのフォルダへドラッグすると一括移動できます。"
          />
        )}
      </ResizableLayout>
    </section>
  )
}

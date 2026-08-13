import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
import { PaneResizer } from '../components/PaneResizer'
import { PreviewPane } from '../components/PreviewPane'
import { PageSizeSelect } from '../components/PageSizeSelect'
import { QueryState } from '../components/QueryState'
import { ResizableLayout } from '../components/ResizableLayout'
import { Spinner } from '../components/Spinner'
import { TruncationNotice } from '../components/TruncationNotice'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useFitPageSize } from '../hooks/useFitPageSize'
import { usePageSize } from '../hooks/usePageSize'
import { useResizablePane } from '../hooks/useResizablePane'
import { useViewMode } from '../hooks/useViewMode'
import type { FileItem } from '../types'

export function BlurryPage() {
  const toast = useToast()
  const view = useViewMode('blurry')
  const pane = useResizablePane('blurry')
  const fitPageSize = useFitPageSize(view.mode, view.size, pane.width ?? 320)
  const { pageSize, setting: pageSizeSetting, setPageSize } = usePageSize('blurry', fitPageSize)
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)
  // null = 未編集。既定値はサーバー設定に追従させる
  const [thresholdInput, setThresholdInput] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [page, setPage] = useState(1)
  const [showFolderPanel, setShowFolderPanel] = useState(false)

  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const threshold = thresholdInput ?? settings.data?.defaults.blur_threshold ?? 20

  const blurry = useQuery({
    queryKey: ['blurry', threshold],
    queryFn: () => api.blurry(threshold),
  })
  const folders = useQuery({
    queryKey: ['folders'],
    queryFn: api.folders,
    enabled: showFolderPanel,
  })

  // /api/blurry はしきい値以下を一括で返すため、表示はクライアント側でページングする
  const all = blurry.data?.items ?? []
  const total = all.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const currentPage = Math.min(page, totalPages)
  const items = all.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const rangeStart = total === 0 ? 0 : (currentPage - 1) * pageSize + 1
  const rangeEnd = (currentPage - 1) * pageSize + items.length

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const selectPage = () => setSelectedIds(items.map((item) => item.id))
  const clearSelection = () => setSelectedIds([])

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`ゴミ箱へ: ${res.moved} 件 / 失敗: ${failed} 件`, 'Blurry')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ移動しました`, 'Blurry')
      }
      setSelectedIds([])
      await blurry.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱への移動に失敗しました')
    },
  })

  const moveMutation = useMutation({
    mutationFn: ({ ids, folder }: { ids: number[]; folder: string }) => api.batchMoveFile(ids, folder),
    onSuccess: async (res, vars) => {
      const failed = res.failed_ids?.length ?? 0
      const folderLabel = vars.folder.split(/[\\/]/).pop() || vars.folder
      if (failed > 0) {
        toast.warning(`${folderLabel} へ移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Blurry')
      } else {
        toast.success(`${res.moved} 件を「${folderLabel}」へ移動しました`, 'Blurry')
      }
      setSelectedIds([])
      await blurry.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '移動に失敗しました')
    },
  })

  const trashSelected = () => {
    if (!selectedIds.length) return
    if (!window.confirm(`${selectedIds.length} 件をゴミ箱へ移動しますか？`)) return
    trashMutation.mutate(selectedIds)
  }

  const handleDrop = (folder: string, ids: number[]) => {
    moveMutation.mutate({ ids, folder })
  }

  const onDragStart = useDraggableFiles(selectedIds)
  const busy = trashMutation.isPending || moveMutation.isPending

  return (
    <section className="page wide">
      <header className="page-header">
        <h2>Blurry Photos</h2>
        <p className="page-subtitle">ぼけスコアが低い画像候補を確認し、まとめてゴミ箱や任意のフォルダへ移動できます。</p>
      </header>
      {/* ツールバーと操作カードはスクロールしても常に見えるようにする */}
      <div className="page-sticky">
        <div className="toolbar">
          <div className="toolbar-group">
            <span className="status-chip">
              <span className="status-dot" />
              {rangeStart}-{rangeEnd} / {total}
            </span>
            <span className="muted">Page {currentPage} / {totalPages}</span>
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
            <PageSizeSelect
              value={pageSizeSetting}
              resolved={fitPageSize}
              onChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
              disabled={busy}
            />
            <button
              className="button secondary"
              disabled={busy || currentPage <= 1}
              onClick={() => {
                setPage(Math.max(1, currentPage - 1))
                setSelectedIds([])
              }}
            >
              Prev
            </button>
            <button
              className="button secondary"
              disabled={busy || currentPage >= totalPages}
              onClick={() => {
                setPage(Math.min(totalPages, currentPage + 1))
                setSelectedIds([])
              }}
            >
              Next
            </button>
          </div>
        </div>
        <article className="card">
          <div className="row">
            <label className="muted">
              ぼけしきい値:
              <input
                className="input"
                type="number"
                min={1}
                max={1000}
                value={threshold}
                onChange={(e) => {
                  setThresholdInput(Math.min(1000, Math.max(1, Number(e.target.value) || 1)))
                  setPage(1)
                  setSelectedIds([])
                }}
                disabled={busy}
                style={{ width: 88, marginLeft: 8 }}
              />
            </label>
            <button className="button secondary" type="button" disabled={busy || !items.length} onClick={selectPage}>
              このページを全選択
            </button>
            <button className="button secondary" type="button" disabled={busy || !selectedIds.length} onClick={clearSelection}>
              選択解除
            </button>
            <button
              className={`button ${showFolderPanel ? '' : 'secondary'}`}
              type="button"
              onClick={() => setShowFolderPanel((v) => !v)}
            >
              {showFolderPanel ? 'パネルを隠す' : 'フォルダパネル'}
            </button>
            <button className="button danger" disabled={busy || !selectedIds.length} onClick={trashSelected}>
              {trashMutation.isPending ? <Spinner size={14} inline /> : null}
              選択をゴミ箱へ ({selectedIds.length})
            </button>
          </div>
          <p className="muted">
            しきい値未満のぼけ候補: {total} 件（このページに {items.length} 件を表示）
          </p>
          <TruncationNotice
            info={blurry.data}
            shown={total}
            subject="ぼけ候補"
            hint="しきい値を下げて絞り込んでください。"
          />
        </article>
      </div>
      <QueryState
        isLoading={blurry.isPending}
        isError={blurry.isError}
        error={blurry.error}
        isEmpty={!blurry.isPending && !blurry.isError && total === 0}
        loadingMessage="ぼけ候補を読み込み中..."
        emptyMessage="ぼけ候補は見つかりませんでした。"
      />
      <ResizableLayout className={`gallery-layout ${showFolderPanel ? 'with-folder' : ''}`} pane={pane}>
        <div
          className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
          style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
        >
          {!blurry.isPending &&
            !blurry.isError &&
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
                <p className="thumb-meta">blur: {item.blur_score ?? '-'}</p>
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
        {showFolderPanel ? (
          <FolderDropPanel
            folders={folders.data?.folders ?? []}
            libraryRoot={folders.data?.root_path}
            counts={folders.data?.counts}
            onDropFiles={handleDrop}
            disabled={busy}
          />
        ) : null}
      </ResizableLayout>
    </section>
  )
}

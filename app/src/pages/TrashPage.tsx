import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { PaneResizer } from '../components/PaneResizer'
import { PreviewPane } from '../components/PreviewPane'
import { PageSizeSelect } from '../components/PageSizeSelect'
import { QueryState } from '../components/QueryState'
import { ResizableLayout } from '../components/ResizableLayout'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { usePageSize } from '../hooks/usePageSize'
import { useResizablePane } from '../hooks/useResizablePane'
import { useViewMode } from '../hooks/useViewMode'
import type { FileItem } from '../types'

export function TrashPage() {
  const toast = useToast()
  const view = useViewMode('trash')
  const pane = useResizablePane('trash')
  const { pageSize, setPageSize } = usePageSize('trash', 60)
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [destinationFolder, setDestinationFolder] = useState('')
  const [page, setPage] = useState(1)

  const trash = useQuery({
    queryKey: ['trash-items', page],
    queryFn: () =>
      api.files(
        new URLSearchParams({
          page: String(page),
          limit: String(pageSize),
          include_trash: 'true',
          status: 'trash',
        }),
      ),
    placeholderData: (prev) => prev,
  })

  const total = trash.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const items = trash.data?.items ?? []
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = (page - 1) * pageSize + items.length

  /** 削除・復元で件数が減って現在ページが範囲外になったら押し戻す */
  const refetchAndClampPage = async () => {
    const { data } = await trash.refetch()
    const newTotalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize))
    setPage((p) => Math.min(p, newTotalPages))
  }
  const folders = useQuery({ queryKey: ['folders'], queryFn: api.folders })

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const restoreMutation = useMutation({
    mutationFn: ({ ids, folder }: { ids: number[]; folder: string }) => api.batchMoveFile(ids, folder),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`復元: ${res.moved} 件 / 失敗: ${failed} 件`, 'Trash')
      } else {
        toast.success(`${res.moved} 件を復元しました`, 'Trash')
      }
      setSelectedIds([])
      await refetchAndClampPage()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '復元に失敗しました')
    },
  })

  const removeFromDbMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      let ok = 0
      const failures: number[] = []
      for (const id of ids) {
        try {
          await api.deleteFileRecord(id)
          ok += 1
        } catch {
          failures.push(id)
        }
      }
      return { ok, failures }
    },
    onSuccess: async ({ ok, failures }) => {
      if (failures.length > 0) {
        toast.warning(`DB削除: ${ok} 件 / 失敗: ${failures.length} 件`, 'Trash')
      } else {
        toast.success(`${ok} 件をDBから削除しました`, 'Trash')
      }
      setSelectedIds([])
      await refetchAndClampPage()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'DB削除に失敗しました')
    },
  })

  const permanentDeleteMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      let deleted = 0
      const blocked: string[] = []
      for (const id of ids) {
        const check = await api.permanentDeleteCheck(id)
        if (!check.allowed) {
          blocked.push(check.blocked_reason ?? `id=${id}`)
          continue
        }
        try {
          await api.permanentDelete(id)
          deleted += 1
        } catch {
          blocked.push(`id=${id} は削除失敗`)
        }
      }
      return { deleted, blocked }
    },
    onSuccess: async ({ deleted, blocked }) => {
      if (blocked.length > 0) {
        toast.warning(
          `完全削除: ${deleted} 件 / 保留・失敗: ${blocked.length} 件 (${blocked[0]})`,
          'Trash',
        )
      } else {
        toast.success(`${deleted} 件を完全削除しました`, 'Trash')
      }
      setSelectedIds([])
      await refetchAndClampPage()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '完全削除に失敗しました')
    },
  })

  const restoreSelected = () => {
    if (!selectedIds.length || !destinationFolder) return
    restoreMutation.mutate({ ids: selectedIds, folder: destinationFolder })
  }

  const removeFromDbSelected = () => {
    if (!selectedIds.length) return
    removeFromDbMutation.mutate(selectedIds)
  }

  const permanentDeleteSelected = () => {
    if (!selectedIds.length) return
    if (!window.confirm(`${selectedIds.length} 件を完全削除しますか？この操作は元に戻せません。`)) return
    permanentDeleteMutation.mutate(selectedIds)
  }

  const busy =
    restoreMutation.isPending || removeFromDbMutation.isPending || permanentDeleteMutation.isPending

  return (
    <section className="page">
      <header className="page-header">
        <h2>Trash</h2>
        <p className="page-subtitle">ゴミ箱項目の復元、DB削除、完全削除をまとめて実行できます。</p>
      </header>
      {/* ツールバーと操作カードはスクロールしても常に見えるようにする */}
      <div className="page-sticky">
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
            <PageSizeSelect
              value={pageSize}
              onChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
              disabled={busy}
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
            isLoading={trash.isPending || folders.isPending}
            isError={trash.isError || folders.isError}
            error={trash.error ?? folders.error}
            isEmpty={false}
            loadingMessage="ゴミ箱データを読み込み中..."
          />
          <p>ゴミ箱件数: {total} 件（このページに {items.length} 件を表示）</p>
          <div className="row">
            <select
              className="input"
              value={destinationFolder}
              onChange={(e) => setDestinationFolder(e.target.value)}
              disabled={busy}
            >
              <option value="">復元先フォルダを選択</option>
              {(folders.data?.folders ?? []).map((folder) => (
                <option key={folder} value={folder}>
                  {folder}
                </option>
              ))}
            </select>
            <button
              className="button"
              disabled={busy || !selectedIds.length || !destinationFolder}
              onClick={restoreSelected}
            >
              {restoreMutation.isPending ? <Spinner size={14} inline /> : null}
              復元 ({selectedIds.length})
            </button>
            <button
              className="button secondary"
              disabled={busy || !selectedIds.length}
              onClick={removeFromDbSelected}
            >
              {removeFromDbMutation.isPending ? <Spinner size={14} inline /> : null}
              DBから削除
            </button>
            <button
              className="button danger"
              disabled={busy || !selectedIds.length}
              onClick={permanentDeleteSelected}
            >
              {permanentDeleteMutation.isPending ? <Spinner size={14} inline /> : null}
              完全削除
            </button>
          </div>
        </article>
      </div>
      <ResizableLayout className="gallery-layout" pane={pane}>
        <div
          className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
          style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
        >
          {!trash.isPending &&
            !trash.isError &&
            items.map((item) => (
              <label
                key={item.id}
                className="thumb-item checkbox-card"
                onClick={() => setPreviewItem(item)}
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
      </ResizableLayout>
    </section>
  )
}

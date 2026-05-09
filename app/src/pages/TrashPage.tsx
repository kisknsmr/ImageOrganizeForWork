import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useViewMode } from '../hooks/useViewMode'

export function TrashPage() {
  const toast = useToast()
  const view = useViewMode('trash')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [destinationFolder, setDestinationFolder] = useState('')

  const trash = useQuery({
    queryKey: ['trash-items'],
    queryFn: () => api.files(new URLSearchParams({ page: '1', limit: '100', include_trash: 'true', status: 'trash' })),
  })
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
      await trash.refetch()
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
      await trash.refetch()
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
      await trash.refetch()
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
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Items: {trash.data?.total ?? 0}
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
        <QueryState
          isLoading={trash.isPending || folders.isPending}
          isError={trash.isError || folders.isError}
          error={trash.error ?? folders.error}
          isEmpty={false}
          loadingMessage="ゴミ箱データを読み込み中..."
        />
        <p>ゴミ箱件数: {trash.data?.total ?? 0}</p>
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
      <div
        className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
        style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
      >
        {!trash.isPending &&
          !trash.isError &&
          (trash.data?.items ?? []).slice(0, 80).map((item) => (
            <label key={item.id} className="thumb-item checkbox-card">
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
    </section>
  )
}

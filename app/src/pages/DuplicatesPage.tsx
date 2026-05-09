import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useViewMode } from '../hooks/useViewMode'

export function DuplicatesPage() {
  const toast = useToast()
  const view = useViewMode('duplicates')
  const [useFullHash, setUseFullHash] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [showFolderPanel, setShowFolderPanel] = useState(false)
  const duplicates = useQuery({
    queryKey: ['duplicates', useFullHash],
    queryFn: () => api.duplicates(useFullHash),
  })
  const folders = useQuery({
    queryKey: ['folders'],
    queryFn: api.folders,
    enabled: showFolderPanel,
  })

  const currentGroup = useMemo(
    () => duplicates.data?.groups.find((g) => g.hash === selectedGroup) ?? null,
    [duplicates.data, selectedGroup],
  )

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Duplicates')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ送りました`, 'Duplicates')
      }
      setSelectedIds([])
      await duplicates.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'ゴミ箱移動に失敗しました')
    },
  })

  const moveMutation = useMutation({
    mutationFn: ({ ids, folder }: { ids: number[]; folder: string }) => api.batchMoveFile(ids, folder),
    onSuccess: async (res, vars) => {
      const failed = res.failed_ids?.length ?? 0
      const folderLabel = vars.folder.split(/[\\/]/).pop() || vars.folder
      if (failed > 0) {
        toast.warning(`${folderLabel} へ移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Duplicates')
      } else {
        toast.success(`${res.moved} 件を「${folderLabel}」へ移動しました`, 'Duplicates')
      }
      setSelectedIds([])
      await duplicates.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '移動に失敗しました')
    },
  })

  const moveSelectedToTrash = () => {
    if (!selectedIds.length || trashMutation.isPending) return
    trashMutation.mutate(selectedIds)
  }

  const handleDrop = (folder: string, ids: number[]) => {
    moveMutation.mutate({ ids, folder })
  }

  const onDragStart = useDraggableFiles(selectedIds)
  const busy = trashMutation.isPending || moveMutation.isPending

  return (
    <section className="page">
      <header className="page-header">
        <h2>Duplicates</h2>
        <p className="page-subtitle">同一ハッシュの画像グループを確認し、不要ファイルを一括でゴミ箱や任意のフォルダへ移動します。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {duplicates.data?.groups.length ?? 0} groups
          </span>
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
          <button className={`button ${!useFullHash ? '' : 'secondary'}`} onClick={() => setUseFullHash(false)}>
            簡易 (高速)
          </button>
          <button className={`button ${useFullHash ? '' : 'secondary'}`} onClick={() => setUseFullHash(true)}>
            完全 (精密)
          </button>
          <button
            className={`button ${showFolderPanel ? '' : 'secondary'}`}
            type="button"
            onClick={() => setShowFolderPanel((v) => !v)}
          >
            {showFolderPanel ? 'パネルを隠す' : 'フォルダパネル'}
          </button>
          <button
            className="button danger"
            disabled={busy || !selectedIds.length}
            onClick={moveSelectedToTrash}
          >
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            選択をゴミ箱へ移動 ({selectedIds.length})
          </button>
        </div>
      </div>
      <div className={`gallery-layout ${showFolderPanel ? 'with-folder' : ''}`}>
        <div>
          <QueryState
            isLoading={duplicates.isPending}
            isError={duplicates.isError}
            error={duplicates.error}
            isEmpty={!duplicates.isPending && !duplicates.isError && (duplicates.data?.groups.length ?? 0) === 0}
            loadingMessage="重複グループを分析中..."
            emptyMessage="重複グループは見つかりませんでした。"
          />
          {!duplicates.isPending && !duplicates.isError && (
            <div className="list-grid">
              {(duplicates.data?.groups ?? []).map((group) => (
                <button
                  key={group.hash}
                  className={`card selectable ${selectedGroup === group.hash ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedGroup(group.hash)
                    setSelectedIds([])
                  }}
                >
                  <h3>{group.hash.slice(0, 12)}...</h3>
                  <p>{group.count} files</p>
                </button>
              ))}
            </div>
          )}
        </div>
        {showFolderPanel ? (
          <FolderDropPanel
            folders={folders.data?.folders ?? []}
            onDropFiles={handleDrop}
            disabled={busy}
          />
        ) : (
          <aside className="preview-pane">
            {!currentGroup && <p className="muted">左から重複グループを選択してください。</p>}
            {currentGroup && (
              <div
                className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
                style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
              >
                {currentGroup.items.map((item) => (
                  <label
                    key={item.id}
                    className="thumb-item checkbox-card"
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
                  </label>
                ))}
              </div>
            )}
          </aside>
        )}
      </div>
    </section>
  )
}

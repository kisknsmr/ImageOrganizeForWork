import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useJobStatus } from '../components/useJobStatus'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useViewMode } from '../hooks/useViewMode'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function DuplicatesPage() {
  const toast = useToast()
  const view = useViewMode('duplicates')
  const { status: jobStatus } = useJobStatus()
  const [useFullHash, setUseFullHash] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [showFolderPanel, setShowFolderPanel] = useState(false)
  const duplicates = useQuery({
    queryKey: ['duplicates', useFullHash],
    queryFn: () => api.duplicates(useFullHash),
  })
  const pendingFullHash = duplicates.data?.pending_full_hash ?? 0
  const fullHashRunning = jobStatus.data?.kind === 'full_hash' && (jobStatus.data?.running ?? false)
  const folders = useQuery({
    queryKey: ['folders'],
    queryFn: api.folders,
    enabled: showFolderPanel,
  })

  const currentGroup = useMemo(
    () => duplicates.data?.groups.find((g) => g.key === selectedGroup) ?? null,
    [duplicates.data, selectedGroup],
  )

  // 完全ハッシュ計算ジョブが終わったら重複一覧を取り直す
  const prevFullHashRunning = useRef(false)
  useEffect(() => {
    if (prevFullHashRunning.current && !fullHashRunning) {
      void duplicates.refetch()
    }
    prevFullHashRunning.current = fullHashRunning
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullHashRunning])

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

  const fullHashMutation = useMutation({
    mutationFn: () => api.duplicatesFullHashStart(),
    onSuccess: async (res) => {
      if (res.started) {
        toast.info(`${res.pending} 件の完全ハッシュを計算中です...`, 'Duplicates')
        await jobStatus.refetch()
      } else {
        toast.info(res.message ?? '計算対象はありません', 'Duplicates')
        await duplicates.refetch()
      }
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '完全ハッシュの計算を開始できませんでした')
    },
  })

  const switchToFullHash = () => {
    setUseFullHash(true)
    setSelectedGroup(null)
    setSelectedIds([])
    // full_hash 列が空のままだと「完全」モードは常に 0 件になるため、
    // 未計算があれば計算ジョブを起動する。
    if (pendingFullHash > 0 && !fullHashRunning && !fullHashMutation.isPending) {
      fullHashMutation.mutate()
    }
  }

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
          <button
            className={`button ${!useFullHash ? '' : 'secondary'}`}
            onClick={() => {
              setUseFullHash(false)
              setSelectedGroup(null)
              setSelectedIds([])
            }}
          >
            簡易 (高速)
          </button>
          <button
            className={`button ${useFullHash ? '' : 'secondary'}`}
            disabled={fullHashRunning || fullHashMutation.isPending}
            onClick={switchToFullHash}
          >
            {fullHashRunning || fullHashMutation.isPending ? <Spinner size={14} inline /> : null}
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
      {fullHashRunning ? (
        <p className="muted">
          完全ハッシュを計算中... {jobStatus.data?.current ?? 0}/{jobStatus.data?.total ?? 0}
        </p>
      ) : null}
      {useFullHash && !fullHashRunning && pendingFullHash > 0 ? (
        <p className="muted">
          未計算の重複候補が {pendingFullHash} 件あります。「完全 (精密)」を押すと計算します。
        </p>
      ) : null}
      <QueryState
        isLoading={duplicates.isPending}
        isError={duplicates.isError}
        error={duplicates.error}
        isEmpty={!duplicates.isPending && !duplicates.isError && (duplicates.data?.groups.length ?? 0) === 0}
        loadingMessage="重複グループを分析中..."
        emptyMessage="重複グループは見つかりませんでした。"
      />
      {!duplicates.isPending && !duplicates.isError && (
        <div className={`workspace ${showFolderPanel ? 'with-folder' : ''}`}>
          {/* 左: グループ選択（一覧するだけなので行リストで十分） */}
          <aside className="pane" aria-label="重複グループ一覧">
            <div className="pane-header">
              <h3 className="section-title">グループ</h3>
              <span className="pane-count">{duplicates.data?.groups.length ?? 0}</span>
            </div>
            <div className="pane-body">
              <div className="group-list" role="listbox" aria-label="重複グループ">
                {(duplicates.data?.groups ?? []).map((group) => (
                  <button
                    key={group.key}
                    type="button"
                    role="option"
                    aria-selected={selectedGroup === group.key}
                    className={`group-item ${selectedGroup === group.key ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedGroup(group.key)
                      setSelectedIds([])
                    }}
                  >
                    <span className="group-item-title mono">{group.hash.slice(0, 16)}</span>
                    <span className="group-item-meta">
                      {group.count} files · {formatSize(group.size)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </aside>

          {/* 中央: 実際に選択・移動する対象。最も広い列を割り当てる */}
          <section className="pane" aria-label="グループ内の画像">
            <div className="pane-header">
              <h3 className="section-title">
                {currentGroup ? `${currentGroup.count} 件の重複` : '画像'}
              </h3>
              {currentGroup && <span className="pane-count">選択 {selectedIds.length}</span>}
            </div>
            <div className="pane-body">
              {!currentGroup ? (
                <p className="muted">左の一覧から重複グループを選択してください。</p>
              ) : (
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
            </div>
          </section>

          {/* 右: 任意表示。画像を隠さず並置するのでドラッグ＆ドロップが成立する */}
          {showFolderPanel && (
            <FolderDropPanel
              folders={folders.data?.folders ?? []}
              libraryRoot={folders.data?.root_path}
              counts={folders.data?.counts}
              onDropFiles={handleDrop}
              disabled={busy}
            />
          )}
        </div>
      )}
    </section>
  )
}

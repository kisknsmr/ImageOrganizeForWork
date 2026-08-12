import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { TruncationNotice } from '../components/TruncationNotice'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useViewMode } from '../hooks/useViewMode'

export function SimilarPage() {
  const toast = useToast()
  const view = useViewMode('similar')
  // null = 未編集。既定値はサーバー設定に追従させる
  const [distanceInput, setDistanceInput] = useState<number | null>(null)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [showFolderPanel, setShowFolderPanel] = useState(false)

  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  // 上限はサーバー側の config.MAX_SIMILARITY_DISTANCE に合わせる。
  // ハードコードしていると config を下げたときに 422 になる。
  const maxDistance = settings.data?.defaults.max_similarity_distance ?? 25
  const distance = distanceInput ?? settings.data?.defaults.similarity_threshold ?? 5

  const similar = useQuery({
    queryKey: ['similar', distance],
    queryFn: () => api.similar(distance),
  })
  const folders = useQuery({
    queryKey: ['folders'],
    queryFn: api.folders,
    enabled: showFolderPanel,
  })

  const groups = similar.data?.groups ?? []
  const currentGroup = useMemo(
    () => similar.data?.groups.find((g) => g.id === selectedGroup) ?? null,
    [similar.data, selectedGroup],
  )

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const selectNonBest = () => {
    if (!currentGroup) return
    setSelectedIds(currentGroup.items.filter((item) => item.id !== currentGroup.best_id).map((item) => item.id))
  }

  const clearSelection = () => setSelectedIds([])

  const trashMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchMoveToTrash(ids),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Similar')
      } else {
        toast.success(`${res.moved} 件をゴミ箱へ送りました`, 'Similar')
      }
      setSelectedIds([])
      await similar.refetch()
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
        toast.warning(`${folderLabel} へ移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Similar')
      } else {
        toast.success(`${res.moved} 件を「${folderLabel}」へ移動しました`, 'Similar')
      }
      setSelectedIds([])
      await similar.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '移動に失敗しました')
    },
  })

  const moveSelectedToTrash = () => {
    if (!selectedIds.length || trashMutation.isPending) return
    if (!window.confirm(`${selectedIds.length} 件をゴミ箱へ移動しますか？`)) return
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
        <h2>Similar Groups</h2>
        <p className="page-subtitle">
          近い特徴量の画像グループを確認し、代表ショットを残して重複ショットをまとめて整理します。
        </p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {groups.length} groups
          </span>
          <label className="muted">
            類似距離:
            <input
              className="input"
              type="number"
              min={0}
              max={maxDistance}
              value={distance}
              onChange={(e) => {
                setDistanceInput(Math.min(maxDistance, Math.max(0, Number(e.target.value) || 0)))
                setSelectedGroup(null)
                setSelectedIds([])
              }}
              disabled={busy}
              style={{ width: 72, marginLeft: 8 }}
            />
          </label>
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
            className={`button ${showFolderPanel ? '' : 'secondary'}`}
            type="button"
            onClick={() => setShowFolderPanel((v) => !v)}
          >
            {showFolderPanel ? 'パネルを隠す' : 'フォルダパネル'}
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={busy || !currentGroup}
            onClick={selectNonBest}
          >
            非代表を選択
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={busy || !selectedIds.length}
            onClick={clearSelection}
          >
            選択解除
          </button>
          <button className="button danger" disabled={busy || !selectedIds.length} onClick={moveSelectedToTrash}>
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            選択をゴミ箱へ移動 ({selectedIds.length})
          </button>
        </div>
      </div>
      <QueryState
        isLoading={similar.isPending}
        isError={similar.isError}
        error={similar.error}
        isEmpty={!similar.isPending && !similar.isError && groups.length === 0}
        loadingMessage="類似グループを分析中..."
        emptyMessage="類似グループは見つかりませんでした。"
      />
      <TruncationNotice
        info={similar.data}
        shown={similar.data?.scanned ?? 0}
        subject="pHash を持つ画像"
        hint="全件を対象にするには先に不要ファイルを整理してください。"
      />
      {!similar.isPending && !similar.isError && (
        <div className={`workspace ${showFolderPanel ? 'with-folder' : ''}`}>
          {/* 左: グループ選択 */}
          <aside className="pane" aria-label="類似グループ一覧">
            <div className="pane-header">
              <h3 className="section-title">グループ</h3>
              <span className="pane-count">{groups.length}</span>
            </div>
            <div className="pane-body">
              <div className="group-list" role="listbox" aria-label="類似グループ">
                {groups.map((group, index) => (
                  <button
                    key={group.id}
                    type="button"
                    role="option"
                    aria-selected={selectedGroup === group.id}
                    className={`group-item ${selectedGroup === group.id ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedGroup(group.id)
                      setSelectedIds([])
                    }}
                  >
                    <span className="group-item-title">グループ {index + 1}</span>
                    <span className="group-item-meta">
                      {group.count} 枚 · 代表 {group.best_id ?? '-'}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </aside>

          {/* 中央: 判断対象の画像を最も広い列に置く */}
          <section className="pane" aria-label="グループ内の画像">
            <div className="pane-header">
              <h3 className="section-title">
                {currentGroup ? `${currentGroup.count} 枚の類似ショット` : '画像'}
              </h3>
              {currentGroup && <span className="pane-count">選択 {selectedIds.length}</span>}
            </div>
            <div className="pane-body">
              {!currentGroup ? (
                <p className="muted">左の一覧から類似グループを選択してください。</p>
              ) : (
                <div
                  className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
                  style={
                    view.mode === 'grid'
                      ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties)
                      : undefined
                  }
                >
                  {currentGroup.items.map((item) => {
                    const isBest = item.id === currentGroup.best_id
                    return (
                      <label
                        key={item.id}
                        className={`thumb-item checkbox-card ${isBest ? 'best' : ''}`}
                        draggable
                        onDragStart={onDragStart(item.id)}
                      >
                        {isBest && <span className="thumb-badge">代表</span>}
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggle(item.id)}
                          disabled={busy}
                        />
                        <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
                        <span>{item.filename}</span>
                      </label>
                    )
                  })}
                </div>
              )}
            </div>
          </section>

          {/* 右: 画像を隠さず並置する */}
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

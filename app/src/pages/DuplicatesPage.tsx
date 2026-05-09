import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { FileDetailPane } from '../components/FileDetailPane'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { ViewControls } from '../components/ViewControls'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import { useViewMode } from '../hooks/useViewMode'
import type { FileItem } from '../types'

export function DuplicatesPage() {
  const toast = useToast()
  const view = useViewMode('duplicates')
  const [useFullHash, setUseFullHash] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null)

  const duplicates = useQuery({
    queryKey: ['duplicates', useFullHash],
    queryFn: () => api.duplicates(useFullHash),
  })

  const currentGroup = useMemo(
    () => duplicates.data?.groups.find((g) => g.hash === selectedGroup) ?? null,
    [duplicates.data, selectedGroup],
  )

  const toggle = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const selectAllExceptFirst = () => {
    if (!currentGroup) return
    const ids = currentGroup.items.slice(1).map((i) => i.id)
    setSelectedIds(ids)
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

  const onDragStart = useDraggableFiles(selectedIds)
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
          {currentGroup && <span className="muted">Selected: {selectedIds.length} / {currentGroup.items.length}</span>}
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
            title="簡易ハッシュが同じファイルに対し、ファイル全体の MD5 を保存します"
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
            disabled={busy || !selectedIds.length}
            onClick={() => trashMutation.mutate(selectedIds)}
          >
            {trashMutation.isPending ? <Spinner size={14} inline /> : null}
            選択をゴミ箱へ ({selectedIds.length})
          </button>
        </div>
      </div>
      {/* 3ペインレイアウト: グループ一覧 | サムネイル一覧 | プレビュー詳細 */}
      <div className="gallery-layout" style={{ gridTemplateColumns: 'minmax(240px, 26vw) 1fr 300px' }}>
        {/* 左: グループ一覧 */}
        <div style={{ overflowY: 'auto', maxHeight: '75vh' }}>
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
                  onClick={() => { setSelectedGroup(group.hash); setSelectedIds([]); setPreviewItem(null) }}
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
        <aside className="preview-pane" style={{ overflowY: 'auto', maxHeight: '75vh' }}>
          {!currentGroup && <p className="muted">左からグループを選択してください。</p>}
          {currentGroup && (
            <div
              className={view.mode === 'grid' ? 'thumb-grid' : 'thumb-list'}
              style={view.mode === 'grid' ? ({ ['--thumb-size' as string]: `${view.size}px` } as React.CSSProperties) : undefined}
            >
              {currentGroup.items.map((item) => (
                <label
                  key={item.id}
                  className={`thumb-item checkbox-card ${selectedIds.includes(item.id) ? 'selected' : ''} ${previewItem?.id === item.id ? 'previewing' : ''}`}
                  draggable
                  onDragStart={onDragStart(item.id)}
                  onClick={() => setPreviewItem(item)}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(item.id)}
                    onChange={() => toggle(item.id)}
                    disabled={busy}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
                  <span>{item.filename}</span>
                </label>
              ))}
            </div>
          )}
        </aside>

        {/* 右: プレビュー＋詳細 */}
        <FileDetailPane item={previewItem} placeholder="サムネイルをクリックしてプレビュー" />
      </div>
    </section>
  )
}

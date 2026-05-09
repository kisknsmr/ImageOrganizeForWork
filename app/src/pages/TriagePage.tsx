import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { FolderDropPanel } from '../components/FolderDropPanel'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'
import { useDraggableFiles } from '../hooks/useDraggableFiles'
import type { FileItem } from '../types'

type TriageAction = 'keep' | 'discard' | 'skip'

const ACTION_LABEL: Record<TriageAction, string> = {
  keep: 'Keep',
  discard: 'Discard',
  skip: 'Skip',
}

export function TriagePage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [lastId, setLastId] = useState(0)
  const [history, setHistory] = useState<Array<{ id: number; prev: FileItem['triage_status'] }>>([])
  const key = useMemo(() => ['triageNext', lastId], [lastId])
  const next = useQuery({ queryKey: key, queryFn: () => api.triageNext(lastId) })
  const current: FileItem | null = next.data?.item ?? null

  const folders = useQuery({ queryKey: ['folders'], queryFn: api.folders })

  const triageMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: TriageAction | null }) => api.triage(id, action),
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'トリアージに失敗しました')
    },
  })

  const moveMutation = useMutation({
    mutationFn: ({ ids, folder }: { ids: number[]; folder: string }) => api.batchMoveFile(ids, folder),
    onSuccess: (res, vars) => {
      const folderLabel = vars.folder.split(/[\\/]/).pop() || vars.folder
      if ((res.failed_ids?.length ?? 0) > 0) {
        toast.warning(`移動失敗: ${res.failed_ids.length} 件`, 'Triage')
      } else {
        toast.success(`「${folderLabel}」へ移動しました`, 'Triage')
      }
      if (current) setLastId(current.id)
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '移動に失敗しました')
    },
  })

  const apply = async (action: TriageAction) => {
    if (!current || triageMutation.isPending) return
    const target = current
    try {
      await triageMutation.mutateAsync({ id: target.id, action })
      setHistory((prev) => [{ id: target.id, prev: target.triage_status }, ...prev].slice(0, 10))
      setLastId(target.id)
      toast.success(`${target.filename} を ${ACTION_LABEL[action]}`, 'Triage')
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    } catch {
      // handled by onError
    }
  }

  const undo = async () => {
    if (triageMutation.isPending) return
    const item = history[0]
    if (!item) {
      toast.info('Undo 履歴はありません')
      return
    }
    try {
      await triageMutation.mutateAsync({ id: item.id, action: null })
      setHistory((prev) => prev.slice(1))
      setLastId(Math.max(0, item.id - 1))
      toast.success('1 件取り消しました', 'Undo')
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    } catch {
      // handled by onError
    }
  }

  const handleDropToFolder = (folder: string, ids: number[]) => {
    moveMutation.mutate({ ids, folder })
  }

  const handleFolderCreated = () => {
    queryClient.invalidateQueries({ queryKey: ['folders'] })
  }

  // current 1枚のみドラッグ対象
  const onDragStart = useDraggableFiles(current ? [current.id] : [])

  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      const target = ev.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return
      if (ev.key === 'ArrowRight' || ev.key.toLowerCase() === 'd') apply('keep')
      if (ev.key === 'ArrowLeft' || ev.key.toLowerCase() === 'a') apply('discard')
      if (ev.key === 'ArrowDown' || ev.key.toLowerCase() === 's') apply('skip')
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') {
        ev.preventDefault()
        undo()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const busy = triageMutation.isPending || moveMutation.isPending

  return (
    <section className="page">
      <header className="page-header">
        <h2>Triage</h2>
        <p className="page-subtitle">キーボード中心で高速に Keep / Discard / Skip を判定します。画像をドラッグしてフォルダへ直接移動もできます。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {busy ? 'Working...' : 'Ready'}
          </span>
          <span className="muted">Undo history: {history.length}</span>
        </div>
        <div className="toolbar-group">
          <button className="button ghost" onClick={undo} disabled={busy || !history.length}>
            {busy ? <Spinner size={14} inline /> : null}
            Undo (Ctrl+Z)
          </button>
        </div>
      </div>
      <div className="gallery-layout with-folder">
        <article className="card">
          <QueryState
            isLoading={next.isPending}
            isError={next.isError}
            error={next.error}
            isEmpty={!next.isPending && !next.isError && !current}
            loadingMessage="次の画像を読み込み中..."
            emptyMessage="未トリアージ画像はありません。"
          />
          {current ? (
            <>
              <img
                className="triage-image"
                src={api.previewUrl(current.id)}
                alt={current.filename}
                draggable
                onDragStart={onDragStart(current.id)}
                style={{ cursor: 'grab' }}
              />
              <h3 className="section-title">{current.filename}</h3>
              <p className="muted mono">{current.path}</p>
              <div className="row">
                <button className="button" onClick={() => apply('keep')} disabled={busy}>
                  {busy ? <Spinner size={14} inline /> : null}
                  Keep (D / →)
                </button>
                <button className="button danger" onClick={() => apply('discard')} disabled={busy}>
                  {busy ? <Spinner size={14} inline /> : null}
                  Discard (A / ←)
                </button>
                <button className="button secondary" onClick={() => apply('skip')} disabled={busy}>
                  {busy ? <Spinner size={14} inline /> : null}
                  Skip (S / ↓)
                </button>
              </div>
            </>
          ) : null}
        </article>
        <FolderDropPanel
          folders={folders.data?.folders ?? []}
          onDropFiles={handleDropToFolder}
          onFolderCreated={handleFolderCreated}
          rootPath={current?.path ? current.path.substring(0, current.path.lastIndexOf(current.path.includes('\\') ? '\\' : '/')) : undefined}
          disabled={busy}
        />
      </div>
    </section>
  )
}

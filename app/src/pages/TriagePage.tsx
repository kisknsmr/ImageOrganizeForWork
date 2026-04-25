import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { FileItem } from '../types'

type TriageAction = 'keep' | 'discard' | 'skip'

export function TriagePage() {
  const [current, setCurrent] = useState<FileItem | null>(null)
  const [lastId, setLastId] = useState(0)
  const [history, setHistory] = useState<Array<{ id: number; prev: FileItem['triage_status'] }>>([])
  const key = useMemo(() => ['triageNext', lastId], [lastId])
  const next = useQuery({ queryKey: key, queryFn: () => api.triageNext(lastId) })

  useEffect(() => {
    if (next.data?.item) {
      setCurrent(next.data.item)
    }
  }, [next.data])

  const triageMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: TriageAction | null }) => api.triage(id, action),
  })

  const apply = async (action: TriageAction) => {
    if (!current) return
    await triageMutation.mutateAsync({ id: current.id, action })
    setHistory((prev) => [{ id: current.id, prev: current.triage_status }, ...prev].slice(0, 10))
    setLastId(current.id)
  }

  const undo = async () => {
    const item = history[0]
    if (!item) return
    await triageMutation.mutateAsync({ id: item.id, action: null })
    setHistory((prev) => prev.slice(1))
    setLastId(Math.max(0, item.id - 1))
  }

  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === 'ArrowRight' || ev.key.toLowerCase() === 'd') apply('keep')
      if (ev.key === 'ArrowLeft' || ev.key.toLowerCase() === 'a') apply('discard')
      if (ev.key === 'ArrowDown' || ev.key.toLowerCase() === 's') apply('skip')
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') undo()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  return (
    <section className="page">
      <h2>Triage</h2>
      <article className="card">
        {current ? (
          <>
            <img className="triage-image" src={api.previewUrl(current.id)} alt={current.filename} />
            <p>{current.filename}</p>
            <div className="row">
              <button className="button" onClick={() => apply('keep')}>
                Keep (D / →)
              </button>
              <button className="button danger" onClick={() => apply('discard')}>
                Discard (A / ←)
              </button>
              <button className="button secondary" onClick={() => apply('skip')}>
                Skip (S / ↓)
              </button>
              <button className="button ghost" onClick={undo}>
                Undo (Ctrl+Z)
              </button>
            </div>
          </>
        ) : (
          <p className="muted">未トリアージ画像はありません。</p>
        )}
      </article>
    </section>
  )
}


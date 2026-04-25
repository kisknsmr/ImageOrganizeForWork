import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { FileItem } from '../types'

export function GalleryPage() {
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<FileItem | null>(null)
  const params = useMemo(() => {
    const p = new URLSearchParams()
    p.set('page', String(page))
    p.set('limit', '80')
    return p
  }, [page])
  const files = useQuery({ queryKey: ['files', page], queryFn: () => api.files(params) })

  return (
    <section className="page">
      <h2>Gallery</h2>
      <div className="gallery-layout">
        <div className="thumb-grid">
          {files.data?.items.map((item) => (
            <button key={item.id} className="thumb-item" onClick={() => setSelected(item)}>
              <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
              <span>{item.filename}</span>
            </button>
          ))}
        </div>
        <aside className="preview-pane">
          {selected ? (
            <>
              <img src={api.previewUrl(selected.id)} alt={selected.filename} />
              <p className="mono">{selected.path}</p>
            </>
          ) : (
            <p className="muted">画像を選択してください</p>
          )}
        </aside>
      </div>
      <div className="row">
        <button className="button secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Prev
        </button>
        <span>Page {page}</span>
        <button className="button secondary" onClick={() => setPage((p) => p + 1)}>
          Next
        </button>
      </div>
    </section>
  )
}


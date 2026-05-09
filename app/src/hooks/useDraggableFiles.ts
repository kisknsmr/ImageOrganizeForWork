import { useCallback } from 'react'
import type { DragEvent } from 'react'

export const FILE_DRAG_MIME = 'application/x-photosortx-files'

export type FileDragPayload = {
  ids: number[]
}

export function readFileDragPayload(event: DragEvent<HTMLElement>): FileDragPayload | null {
  const raw = event.dataTransfer.getData(FILE_DRAG_MIME)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as FileDragPayload
    if (!parsed || !Array.isArray(parsed.ids)) return null
    const ids = parsed.ids.filter((x) => Number.isFinite(x))
    return { ids }
  } catch {
    return null
  }
}

export function hasFileDrag(event: DragEvent<HTMLElement>): boolean {
  return Array.from(event.dataTransfer.types).includes(FILE_DRAG_MIME)
}

export function useDraggableFiles(selectedIds: number[]) {
  return useCallback(
    (id: number) => (event: DragEvent<HTMLElement>) => {
      const ids =
        selectedIds.length > 1 && selectedIds.includes(id) ? selectedIds : [id]
      const payload: FileDragPayload = { ids }
      event.dataTransfer.setData(FILE_DRAG_MIME, JSON.stringify(payload))
      event.dataTransfer.setData('text/plain', `${ids.length} file(s)`)
      event.dataTransfer.effectAllowed = 'move'
      const target = event.currentTarget as HTMLElement
      target.classList.add('dragging')
      const cleanup = () => {
        target.classList.remove('dragging')
        target.removeEventListener('dragend', cleanup)
      }
      target.addEventListener('dragend', cleanup)
    },
    [selectedIds],
  )
}

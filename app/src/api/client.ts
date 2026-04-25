import type { FileItem, LibraryStats, PagedFiles, ScanJob } from '../types'

const API_BASE = 'http://127.0.0.1:8765'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return (await res.json()) as T
}

export const api = {
  health: () => request<{ ok: boolean; version: string; stats: LibraryStats }>('/api/health'),
  stats: () => request<LibraryStats>('/api/library/stats'),
  scanStart: (rootPath: string) =>
    request<ScanJob>('/api/scan/start', { method: 'POST', body: JSON.stringify({ root_path: rootPath }) }),
  scanStatus: () => request<ScanJob>('/api/scan/status'),
  analyzeStart: () => request<{ started: boolean; message?: string; job: ScanJob }>('/api/analyze/start', { method: 'POST' }),
  files: (params: URLSearchParams) => request<PagedFiles>(`/api/files?${params.toString()}`),
  triage: (id: number, action: 'keep' | 'discard' | 'skip' | null) =>
    request(`/api/files/${id}/triage`, { method: 'POST', body: JSON.stringify({ action }) }),
  triageNext: (afterId = 0) => request<{ item: FileItem | null }>(`/api/triage/next?after_id=${afterId}`),
  blurry: (threshold = 20) => request<{ items: FileItem[] }>(`/api/blurry?threshold=${threshold}`),
  duplicates: () => request<{ groups: Array<{ hash: string; count: number; items: FileItem[] }> }>('/api/duplicates'),
  similar: (distance = 5) =>
    request<{ groups: Array<{ id: string; count: number; best_id: number | null; items: FileItem[] }> }>(
      `/api/similar?distance=${distance}`,
    ),
  previewUrl: (id: number) => `${API_BASE}/api/files/${id}/preview`,
  thumbnailUrl: (id: number) => `${API_BASE}/api/files/${id}/thumbnail`,
}


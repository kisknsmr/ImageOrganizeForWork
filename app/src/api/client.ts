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
  analyzeFullHashStart: () =>
    request<{ started: boolean; message?: string; job: ScanJob }>('/api/analyze/full-hash/start', { method: 'POST' }),
  files: (params: URLSearchParams) => request<PagedFiles>(`/api/files?${params.toString()}`),
  triage: (id: number, action: 'keep' | 'discard' | 'skip' | null) =>
    request(`/api/files/${id}/triage`, { method: 'POST', body: JSON.stringify({ action }) }),
  moveToTrash: (id: number) => request(`/api/files/${id}/trash`, { method: 'POST' }),
  batchMoveToTrash: (fileIds: number[]) =>
    request<{ ok: boolean; moved: number; failed_ids: number[] }>('/api/files/batch-trash', {
      method: 'POST',
      body: JSON.stringify({ file_ids: fileIds }),
    }),
  deleteFileRecord: (id: number) => request(`/api/files/${id}`, { method: 'DELETE' }),
  permanentDeleteCheck: (id: number) =>
    request<{ allowed: boolean; blocked_reason: string | null }>(`/api/files/${id}/permanent-delete-check`),
  permanentDelete: (id: number) => request(`/api/files/${id}/permanent-delete`, { method: 'POST' }),
  moveFile: (id: number, destinationFolder: string) =>
    request(`/api/files/${id}/move`, { method: 'POST', body: JSON.stringify({ destination_folder: destinationFolder }) }),
  batchMoveFile: (fileIds: number[], destinationFolder: string) =>
    request<{ ok: boolean; moved: number; failed_ids: number[] }>('/api/files/batch-move', {
      method: 'POST',
      body: JSON.stringify({ file_ids: fileIds, destination_folder: destinationFolder }),
    }),
  tinyFiles: (maxSize = 50 * 1024) =>
    request<{ items: FileItem[]; max_size: number }>(`/api/tiny?max_size=${maxSize}`),
  getSettings: () =>
    request<Record<string, string | null>>('/api/settings'),
  saveSetting: (key: string, value: string) =>
    request<{ ok: boolean }>('/api/settings', {
      method: 'POST',
      body: JSON.stringify({ key, value }),
    }),
  folders: () => request<{ folders: string[] }>('/api/folders'),
  createFolder: (path: string) =>
    request<{ ok: boolean; path: string }>('/api/folders', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  triageNext: (afterId = 0) => request<{ item: FileItem | null }>(`/api/triage/next?after_id=${afterId}`),
  blurry: (threshold = 20) => request<{ items: FileItem[] }>(`/api/blurry?threshold=${threshold}`),
  duplicates: (useFullHash = false) =>
    request<{ groups: Array<{ hash: string; count: number; items: FileItem[] }> }>(
      `/api/duplicates?use_full_hash=${useFullHash ? 'true' : 'false'}`,
    ),
  similar: (distance = 5) =>
    request<{ groups: Array<{ id: string; count: number; best_id: number | null; items: FileItem[] }> }>(
      `/api/similar?distance=${distance}`,
    ),
  previewUrl: (id: number) => `${API_BASE}/api/files/${id}/preview`,
  thumbnailUrl: (id: number) => `${API_BASE}/api/files/${id}/thumbnail`,
}


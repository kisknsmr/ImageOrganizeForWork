import type { AppSettings, FileItem, LibraryStats, PagedFiles, ScanJob } from '../types'

const API_BASE = 'http://127.0.0.1:8765'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      ...init,
    })
  } catch (cause) {
    throw new Error(
      `APIサーバー(${API_BASE})に接続できません。バックエンド(uvicorn)が起動しているか確認してください。`,
      { cause },
    )
  }
  if (!res.ok) {
    // FastAPI は失敗理由を JSON の detail に入れて返す。拾えれば表示する。
    let detail = ''
    try {
      const body = (await res.clone().json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail != null) detail = JSON.stringify(body.detail)
    } catch {
      // JSON でない/本文なし → ステータス文言にフォールバック
    }
    throw new Error(detail ? `${detail} (HTTP ${res.status})` : `HTTP ${res.status} ${res.statusText}`)
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
  folders: () => request<{ folders: string[] }>('/api/folders'),
  createFolder: (path: string) =>
    request<{ ok: boolean; path: string }>('/api/folders', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  triageNext: (afterId = 0) => request<{ item: FileItem | null }>(`/api/triage/next?after_id=${afterId}`),
  blurry: (threshold = 20) => request<{ items: FileItem[] }>(`/api/blurry?threshold=${threshold}`),
  tiny: (maxSizeKb = 10) =>
    request<{ max_size_kb: number; items: FileItem[] }>(`/api/tiny?max_size_kb=${maxSizeKb}`),
  settings: () => request<AppSettings>('/api/settings'),
  updateSettings: (payload: { trash_folder?: string }) =>
    request<AppSettings>('/api/settings', { method: 'POST', body: JSON.stringify(payload) }),
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


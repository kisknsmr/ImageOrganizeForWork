import type {
  AppSettings,
  BlurryResponse,
  DuplicatesResponse,
  FileInfo,
  FileItem,
  FolderList,
  LibraryClearResult,
  LibraryClearScope,
  LibraryStats,
  OrganizeApplyResult,
  OrganizeCapabilities,
  OrganizePreview,
  PagedFiles,
  PreprocessCheck,
  PreprocessMode,
  ScanCheck,
  ScanJob,
  SimilarResponse,
  TinyResponse,
} from '../types'

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
  /** 直前のジョブ結果の表示を消す（実行中は 409） */
  jobsReset: () => request<ScanJob>('/api/jobs/reset', { method: 'POST' }),
  /** 実行中のジョブを一時停止（バッチ境界で効く） */
  jobsPause: () => request<ScanJob>('/api/jobs/pause', { method: 'POST' }),
  jobsResume: () => request<ScanJob>('/api/jobs/resume', { method: 'POST' }),
  /** 実行中のジョブを中止。処理済みの分は DB に残る */
  jobsCancel: () => request<ScanJob>('/api/jobs/cancel', { method: 'POST' }),
  scanCheck: (rootPath: string) =>
    request<ScanCheck>(`/api/scan/check?root_path=${encodeURIComponent(rootPath)}`),
  analyzeStart: () => request<{ started: boolean; message?: string; job: ScanJob }>('/api/analyze/start', { method: 'POST' }),
  analyzeReset: (rootPath: string) =>
    request<{ reset: number }>('/api/analyze/reset', { method: 'POST', body: JSON.stringify({ root_path: rootPath }) }),
  /** 前回の読み込み記録を消す。ディスク上のファイルは削除しない */
  libraryClear: (scope: LibraryClearScope) =>
    request<LibraryClearResult>('/api/library/clear', {
      method: 'POST',
      body: JSON.stringify({ scope }),
    }),
  preprocessStart: (rootPath: string, mode: PreprocessMode = 'incremental') =>
    request<ScanJob>('/api/preprocess/start', {
      method: 'POST',
      body: JSON.stringify({ root_path: rootPath, mode }),
    }),
  /** 振り分け対象の事前カウント。scanCheck とは対象範囲が異なる */
  preprocessCheck: (rootPath: string, mode: PreprocessMode = 'incremental') =>
    request<PreprocessCheck>(
      `/api/preprocess/check?root_path=${encodeURIComponent(rootPath)}&mode=${mode}`,
    ),
  files: (params: URLSearchParams) => request<PagedFiles>(`/api/files?${params.toString()}`),
  /** プレビューペイン用のファイル詳細（サイズ・寸法はディスクの実値） */
  fileInfo: (id: number) => request<FileInfo>(`/api/files/${id}/info`),
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
  folders: () => request<FolderList>('/api/folders'),
  createFolder: (path: string) =>
    request<{ ok: boolean; path: string }>('/api/folders', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  triageNext: (afterId = 0) => request<{ item: FileItem | null }>(`/api/triage/next?after_id=${afterId}`),
  /** triage_status で絞り込んだファイル一覧（Discard 済みの回収などに使う） */
  filesByTriage: (triageStatus: 'keep' | 'discard' | 'skip', page = 1, limit = 200) =>
    request<PagedFiles>(
      `/api/files?${new URLSearchParams({
        page: String(page),
        limit: String(limit),
        triage_status: triageStatus,
      }).toString()}`,
    ),
  blurry: (threshold = 20) => request<BlurryResponse>(`/api/blurry?threshold=${threshold}`),
  tiny: (maxSizeKb = 10) => request<TinyResponse>(`/api/tiny?max_size_kb=${maxSizeKb}`),
  settings: () => request<AppSettings>('/api/settings'),
  updateSettings: (payload: { trash_folder?: string }) =>
    request<AppSettings>('/api/settings', { method: 'POST', body: JSON.stringify(payload) }),
  duplicates: (useFullHash = false) =>
    request<DuplicatesResponse>(`/api/duplicates?use_full_hash=${useFullHash ? 'true' : 'false'}`),
  duplicatesFullHashStart: () =>
    request<{ started: boolean; pending: number; message?: string; job: ScanJob }>(
      '/api/duplicates/full-hash/start',
      { method: 'POST' },
    ),
  similar: (distance = 5) => request<SimilarResponse>(`/api/similar?distance=${distance}`),
  organizeCapabilities: () => request<OrganizeCapabilities>('/api/organize/capabilities'),
  organizePreview: (gapHours = 6, minGroupSize = 1, maxItemsPerGroup = 8) =>
    request<OrganizePreview>(
      `/api/organize/preview?gap_hours=${gapHours}&min_group_size=${minGroupSize}&max_items_per_group=${maxItemsPerGroup}`,
    ),
  organizeApply: (destinationRoot: string, groups: Array<{ name: string; file_ids: number[] }>) =>
    request<OrganizeApplyResult>('/api/organize/apply', {
      method: 'POST',
      body: JSON.stringify({ destination_root: destinationRoot, groups }),
    }),
  previewUrl: (id: number) => `${API_BASE}/api/files/${id}/preview`,
  thumbnailUrl: (id: number) => `${API_BASE}/api/files/${id}/thumbnail`,
}


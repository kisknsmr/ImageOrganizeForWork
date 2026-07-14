export type ScanJob = {
  kind: string
  running: boolean
  current: number
  total: number
  percent: number
  message: string
  started_at?: number | null
  finished_at?: number | null
  error?: string | null
}

export type FileItem = {
  id: number
  path: string
  filename: string
  extension: string
  size: number
  mtime: number
  status: string
  hash_value?: string | null
  p_hash?: string | null
  blur_score?: number | null
  full_hash?: string | null
  quality_score?: number | null
  content_type?: string | null
  triage_status?: 'keep' | 'discard' | 'skip' | null
  is_best_in_group?: boolean
  scan_phase?: string | null
}

export type PagedFiles = {
  page: number
  limit: number
  total: number
  items: FileItem[]
}

export type LibraryStats = {
  total: number
  analyzed: number
  unprocessed: number
  triaged: number
  trashed: number
  root_path?: string | null
}

export type OrganizeGroup = {
  id: string
  suggested_name: string
  start_time: string | null
  end_time: string | null
  count: number
  file_ids: number[]
  items: FileItem[]
}

export type OrganizePreview = {
  gap_hours: number
  min_group_size: number
  groups: OrganizeGroup[]
}

export type OrganizeCapabilities = {
  time: boolean
  content: boolean
  hybrid: boolean
  ai_dependencies_installed: boolean
}

export type OrganizeApplyResult = {
  ok: boolean
  moved: number
  failed_ids: number[]
  folders: Array<{ name: string; path: string; moved: number; failed_ids: number[]; error?: string }>
}

export type AppSettings = {
  version: string
  root_path?: string | null
  trash_folder: string
  db_name: string
  defaults: {
    blur_threshold: number
    similarity_threshold: number
    max_similarity_distance: number
    min_file_size_kb: number
  }
  extensions: {
    image: string[]
    video: string[]
  }
  stats: LibraryStats
}


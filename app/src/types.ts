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

export type SeparateItem = {
  src: string
  dst: string
  kind: 'image' | 'video'
  rel_path: string
}

export type OrganizeItem = {
  id: number
  path: string
  filename: string
  mtime: number
  is_representative: boolean
}

export type OrganizeSuggestion = {
  group_id: string
  suggested_name: string
  reason: string
  date_range: { start: string; end: string }
  items: OrganizeItem[]
}

export type LibraryStats = {
  total: number
  analyzed: number
  unprocessed: number
  triaged: number
  trashed: number
  root_path?: string | null
}


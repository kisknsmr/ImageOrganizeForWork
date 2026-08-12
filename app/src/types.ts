export type PreprocessResult = {
  stopped: boolean
  moved: number
  skipped: number
  total: number
  pictures: number
  movies: number
  others: number
}

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
  result?: PreprocessResult | null
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

export type ScanCheck = {
  root_path: string
  valid: boolean
  disk_count: number
  total: number
  analyzed: number
  unprocessed: number
  already_up_to_date: boolean
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

/** 一覧系エンドポイントが上限で打ち切られたかを伝える共通フィールド */
export type TruncationInfo = {
  /** 打ち切り前の候補総数 */
  available: number
  /** 適用された上限 */
  limit: number
  truncated: boolean
}

export type BlurryResponse = TruncationInfo & {
  items: FileItem[]
}

export type TinyResponse = TruncationInfo & {
  max_size_kb: number
  items: FileItem[]
}

export type SimilarGroup = {
  id: string
  count: number
  best_id: number | null
  items: FileItem[]
}

export type SimilarResponse = TruncationInfo & {
  distance: number
  groups: SimilarGroup[]
  /** 実際に比較した件数 */
  scanned: number
}

export type DuplicateGroup = {
  /** ハッシュとサイズの組。同一ハッシュでもサイズ違いは別グループ */
  key: string
  hash: string
  size: number
  count: number
  items: FileItem[]
}

export type DuplicatesResponse = {
  groups: DuplicateGroup[]
  use_full_hash: boolean
  /** 完全ハッシュが未計算の重複候補ファイル数 */
  pending_full_hash: number
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


/** GET /api/folders — 移動先候補。UI 側でツリーに組み直して表示する */
export type FolderList = {
  folders: string[]
  root_path?: string | null
  /** 絶対パス → そのフォルダ直下のファイル数 */
  counts?: Record<string, number>
}

/** 読み込み記録の消去範囲。current = 現在のライブラリのみ / all = 全記録 */
export type LibraryClearScope = 'current' | 'all'

/** POST /api/library/clear の結果 */
export type LibraryClearResult = {
  /** 消したファイル記録の件数 */
  deleted: number
  /** 復元できなくなるため残したゴミ箱の件数 */
  kept_trash: number
  root_path: string | null
  scope: LibraryClearScope
}

/** GET /api/preprocess/check — 振り分け対象の事前カウント（実行結果の total と一致する） */
export type PreprocessCheck = {
  root_path: string
  valid: boolean
  total: number
  pictures: number
  movies: number
  others: number
}

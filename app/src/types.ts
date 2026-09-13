export type PreprocessResult = {
  stopped: boolean
  moved: number
  skipped: number
  /** 振り分け対象の件数 */
  total: number
  /** フォルダ内の全ファイル数（ゴミ箱を除く）= total + already_sorted */
  all_files: number
  /** 既に正しいカテゴリにあり、動かす必要がなかった件数 */
  already_sorted: number
  /** まだ振り分けられていなかった件数 */
  unsorted: number
  /** 別カテゴリへ移し直すべきだった件数 */
  misplaced: number
  /** 実際に移し直した件数 */
  rechecked: number
  full: boolean
  pictures: number
  movies: number
  others: number
}

/** 空フォルダ削除の結果 */
export type EmptyDirsResult = {
  stopped: boolean
  /** 実際に削除できたフォルダ数 */
  removed: number
  /** 削除できなかったフォルダ数（判定後に中身が増えた・権限不足など） */
  failed: number
  /** 削除対象として見つかった数 */
  total: number
  /** 消したフォルダのうち、いちばん深かったものの階層 */
  max_depth: number
  /** 一緒に消した Thumbs.db などの残骸ファイル数 */
  junk_removed: number
}

export type JobResult = PreprocessResult | EmptyDirsResult

/** ジョブ結果はジョブ種別ごとに形が違うので、kind ではなく中身で見分ける */
export function isPreprocessResult(result: JobResult | null | undefined): result is PreprocessResult {
  return !!result && 'moved' in result
}

export function isEmptyDirsResult(result: JobResult | null | undefined): result is EmptyDirsResult {
  return !!result && 'removed' in result
}

export type ScanJob = {
  kind: string
  running: boolean
  /** 実行中だがユーザー操作で待機している */
  paused?: boolean
  current: number
  total: number
  percent: number
  message: string
  started_at?: number | null
  finished_at?: number | null
  error?: string | null
  result?: JobResult | null
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

/** 振り分けの走査モード。full はカテゴリフォルダの中も見直す */
export type PreprocessMode = 'incremental' | 'full'

/** GET /api/preprocess/check — 振り分け対象の事前カウント（実行結果の total と一致する） */
export type PreprocessCheck = {
  root_path: string
  valid: boolean
  /** 走査したファイル数 = total + already_sorted（差分モードではカテゴリ内を数えない） */
  all_files: number
  /** 振り分け対象 = unsorted + misplaced */
  total: number
  /** まだ振り分けられていない（カテゴリフォルダの外にある） */
  unsorted: number
  /** 既に振り分け済みだが、今の基準では別カテゴリに入るべきもの */
  misplaced: number
  /** 既に正しいカテゴリにあり、動かす必要がない件数 */
  already_sorted: number
  full: boolean
  pictures: number
  movies: number
  others: number
}

/** GET /api/preprocess/empty-dirs — 空フォルダの事前カウント */
export type EmptyDirsCheck = {
  root_path: string
  valid: boolean
  /** 削除できる空フォルダの数（連なっている場合は 1 つずつ数える） */
  total: number
  /** いちばん深い対象の階層 */
  max_depth: number
  /** 確認用に、対象パス（root からの相対）を先頭 20 件だけ */
  samples: string[]
}

/** GET /api/files/{id}/info — プレビューペイン用のファイル詳細 */
export type FileInfo = {
  id: number
  path: string
  filename: string
  extension: string
  content_type: string
  /** ディスク上に実在するか。false ならサイズ・寸法は当てにならない */
  exists: boolean
  size: number
  mtime: number
  width: number | null
  height: number | null
}

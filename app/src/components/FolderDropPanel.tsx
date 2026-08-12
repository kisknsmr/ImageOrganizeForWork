import { useMemo, useState } from 'react'
import type { DragEvent, KeyboardEvent } from 'react'
import { api } from '../api/client'
import { hasFileDrag, readFileDragPayload } from '../hooks/useDraggableFiles'

type FolderDropPanelProps = {
  folders: string[]
  onDropFiles: (folder: string, ids: number[]) => void
  onFolderCreated?: (path: string) => void
  /** 新規フォルダ作成時の基準パス（表示用のライブラリルートとは別） */
  rootPath?: string
  /** ツリーの起点として畳んで表示するライブラリルート */
  libraryRoot?: string | null
  /** 絶対パス → 直下のファイル数 */
  counts?: Record<string, number>
  title?: string
  hint?: string
  disabled?: boolean
}

type TreeNode = {
  /** 絶対パス。ドロップ先として使う */
  path: string
  /** 表示名。中間フォルダを畳んだ場合は "a\b" のように連結される */
  label: string
  depth: number
  /** このフォルダ直下のファイル数 */
  count: number
  /** 配下も含めた合計ファイル数 */
  total: number
  children: TreeNode[]
}

type RawNode = {
  seg: string
  path: string
  count: number
  children: Map<string, RawNode>
}

/**
 * 絶対パスの配列をフォルダツリーへ組み直す。
 *
 * フラットな絶対パスを 1 行ずつ並べると、先頭の共通部分（C:\Users\...）だけが
 * 表示されて末尾が省略され、どのフォルダなのか区別できなくなる。
 * 階層構造そのものを見せて、各行はフォルダ名だけを持たせる。
 */
function buildTree(paths: string[], counts?: Record<string, number>): TreeNode[] {
  if (paths.length === 0) return []
  const sep = paths.some((p) => p.includes('\\')) ? '\\' : '/'
  const root: RawNode = { seg: '', path: '', count: 0, children: new Map() }

  for (const fullPath of paths) {
    const segments = fullPath.split(/[\\/]/).filter(Boolean)
    if (segments.length === 0) continue
    // POSIX の絶対パスは先頭の "/" が split で落ちるので復元する
    const absolutePrefix = fullPath.startsWith('/') ? sep : ''
    let node = root
    let accumulated = ''
    segments.forEach((seg, index) => {
      accumulated = index === 0 ? `${absolutePrefix}${seg}` : `${accumulated}${sep}${seg}`
      let child = node.children.get(seg)
      if (!child) {
        child = { seg, path: accumulated, count: 0, children: new Map() }
        node.children.set(seg, child)
      }
      node = child
    })
    node.count = counts?.[fullPath] ?? 0
  }

  const convert = (raw: RawNode, depth: number): TreeNode => {
    // ファイルを持たず子が 1 つだけの中間フォルダは 1 行にまとめる（無意味な階層を減らす）
    let label = raw.seg
    let current = raw
    while (current.children.size === 1 && current.count === 0) {
      const only = [...current.children.values()][0]
      label = `${label}${sep}${only.seg}`
      current = only
    }
    const children = [...current.children.values()]
      .sort((a, b) => a.seg.localeCompare(b.seg, 'ja'))
      .map((child) => convert(child, depth + 1))
    const total = current.count + children.reduce((sum, child) => sum + child.total, 0)
    // 最上位行はドライブや先頭の "/" まで含めた完全なパスを見せる
    return {
      path: current.path,
      label: depth === 0 ? current.path : label,
      depth,
      count: current.count,
      total,
      children,
    }
  }

  return [...root.children.values()]
    .sort((a, b) => a.seg.localeCompare(b.seg, 'ja'))
    .map((child) => convert(child, 0))
}

/** 検索語に一致するノードと、その祖先だけを残す */
function filterTree(nodes: TreeNode[], needle: string): TreeNode[] {
  if (!needle) return nodes
  const lowered = needle.toLowerCase()
  const walk = (node: TreeNode): TreeNode | null => {
    // 自分が一致したら配下はそのまま残す（絞り込んだ先を辿れるように）
    if (node.path.toLowerCase().includes(lowered)) return node
    const children = node.children.map(walk).filter((n): n is TreeNode => n !== null)
    return children.length > 0 ? { ...node, children } : null
  }
  return nodes.map(walk).filter((n): n is TreeNode => n !== null)
}

/** 展開状態を反映して、描画する行の一次元配列にする */
function flatten(nodes: TreeNode[], isExpanded: (path: string) => boolean): TreeNode[] {
  const rows: TreeNode[] = []
  const walk = (node: TreeNode, depth: number) => {
    rows.push({ ...node, depth })
    if (node.children.length > 0 && isExpanded(node.path)) {
      node.children.forEach((child) => walk(child, depth + 1))
    }
  }
  nodes.forEach((node) => walk(node, 0))
  return rows
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d={open ? 'M4 6.5L8 10.5L12 6.5' : 'M6.5 4L10.5 8L6.5 12'}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function FolderIcon({ open }: { open: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true">
      {open ? (
        <path
          d="M2 5A1.5 1.5 0 0 1 3.5 3.5H6L7.5 5.5h5A1.5 1.5 0 0 1 14 7l-.9 4.7a1.5 1.5 0 0 1-1.5 1.3H3.4a1.5 1.5 0 0 1-1.5-1.5V5Z"
          fill="currentColor"
        />
      ) : (
        <path
          d="M2 4.5A1.5 1.5 0 0 1 3.5 3H6l1.5 2H12.5A1.5 1.5 0 0 1 14 6.5V12a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12V4.5Z"
          fill="currentColor"
        />
      )}
    </svg>
  )
}

export function FolderDropPanel({
  folders,
  onDropFiles,
  onFolderCreated,
  rootPath,
  libraryRoot,
  counts,
  title = 'フォルダへドラッグして移動',
  hint = '画像をここへドラッグするとフォルダへ移動できます。',
  disabled,
}: FolderDropPanelProps) {
  const [overFolder, setOverFolder] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const tree = useMemo(() => buildTree(folders, counts), [folders, counts])
  const visibleTree = useMemo(() => filterTree(tree, filter.trim()), [tree, filter])

  /*
   * 既定は「展開」。閉じたものだけを覚える方式にすると、フォルダが増えても
   * 勝手に畳まれない。検索中は一致箇所まで必ず辿れるよう常に全開にする。
   */
  const searching = filter.trim().length > 0
  const isExpanded = (path: string) => searching || !collapsed.has(path)

  const rows = useMemo(() => flatten(visibleTree, isExpanded), [visibleTree, collapsed, searching])

  const toggleNode = (path: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const handleDragOver = (folder: string) => (event: DragEvent<HTMLElement>) => {
    if (disabled) return
    if (!hasFileDrag(event)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
    if (overFolder !== folder) setOverFolder(folder)
  }

  const handleDragLeave = (folder: string) => (event: DragEvent<HTMLElement>) => {
    if (overFolder !== folder) return
    const related = event.relatedTarget as Node | null
    if (related && (event.currentTarget as Node).contains(related)) return
    setOverFolder(null)
  }

  const handleDrop = (folder: string) => (event: DragEvent<HTMLElement>) => {
    if (disabled) return
    const payload = readFileDragPayload(event)
    setOverFolder(null)
    if (!payload || payload.ids.length === 0) return
    event.preventDefault()
    onDropFiles(folder, payload.ids)
  }

  const resolvePath = (name: string): string => {
    const trimmed = name.trim()
    if (!rootPath) return trimmed
    // スラッシュ・バックスラッシュ両対応でルートパスと結合
    const sep = rootPath.includes('\\') ? '\\' : '/'
    return `${rootPath}${sep}${trimmed.replace(/\//g, sep)}`
  }

  const handleCreateFolder = async () => {
    const name = newFolderName.trim()
    if (!name) return
    setCreateBusy(true)
    setCreateError(null)
    try {
      const result = await api.createFolder(resolvePath(name))
      setNewFolderName('')
      setCreatingFolder(false)
      onFolderCreated?.(result.path)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'フォルダの作成に失敗しました')
    } finally {
      setCreateBusy(false)
    }
  }

  const handleCreateKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleCreateFolder()
    if (e.key === 'Escape') {
      setCreatingFolder(false)
      setNewFolderName('')
      setCreateError(null)
    }
  }

  return (
    <aside className={`folder-drop-panel ${disabled ? 'disabled' : ''}`} aria-label="フォルダパネル">
      <header className="folder-drop-header">
        <h3 className="section-title">{title}</h3>
        <p className="muted">{hint}</p>
        {libraryRoot && (
          <p className="folder-root mono" title={libraryRoot}>
            {libraryRoot}
          </p>
        )}
      </header>

      <input
        type="search"
        className="input"
        placeholder="フォルダを検索..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        disabled={disabled}
      />

      <div className="folder-drop-list" role="tree" aria-label="フォルダツリー">
        {rows.length === 0 && <p className="muted">該当するフォルダがありません。</p>}
        {rows.map((node) => {
          const hasChildren = node.children.length > 0
          const open = hasChildren && isExpanded(node.path)
          return (
            <div
              key={node.path}
              role="treeitem"
              aria-level={node.depth + 1}
              aria-expanded={hasChildren ? open : undefined}
              className={`folder-tree-row drop-zone ${overFolder === node.path ? 'over' : ''}`}
              style={{ paddingLeft: 4 + node.depth * 16 }}
              onDragOver={handleDragOver(node.path)}
              onDragEnter={handleDragOver(node.path)}
              onDragLeave={handleDragLeave(node.path)}
              onDrop={handleDrop(node.path)}
              title={node.path}
            >
              {hasChildren ? (
                <button
                  type="button"
                  className="folder-tree-toggle"
                  onClick={() => toggleNode(node.path)}
                  aria-label={open ? '折りたたむ' : '展開する'}
                  tabIndex={-1}
                >
                  <ChevronIcon open={open} />
                </button>
              ) : (
                <span className="folder-tree-toggle" aria-hidden="true" />
              )}
              <span className="folder-tree-icon" aria-hidden="true">
                <FolderIcon open={open} />
              </span>
              <span className="folder-tree-name">{node.label}</span>
              {node.total > 0 && <span className="folder-tree-count">{node.total}</span>}
            </div>
          )
        })}
      </div>

      <div className="folder-panel-footer">
        {creatingFolder ? (
          <div className="folder-create-form">
            <input
              type="text"
              className="input"
              placeholder={rootPath ? `${rootPath}\\フォルダ名` : 'フォルダの絶対パス'}
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={handleCreateKeyDown}
              disabled={createBusy}
              autoFocus
            />
            {createError && <p className="folder-create-error">{createError}</p>}
            <div className="row">
              <button
                className="button"
                onClick={handleCreateFolder}
                disabled={createBusy || !newFolderName.trim()}
              >
                {createBusy ? '作成中...' : '作成'}
              </button>
              <button
                className="button ghost"
                onClick={() => { setCreatingFolder(false); setNewFolderName(''); setCreateError(null) }}
                disabled={createBusy}
              >
                キャンセル
              </button>
            </div>
          </div>
        ) : (
          <button
            className="button ghost folder-create-btn"
            onClick={() => setCreatingFolder(true)}
            disabled={disabled}
          >
            + 新規フォルダ
          </button>
        )}
      </div>
    </aside>
  )
}

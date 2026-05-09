import { useState } from 'react'
import type { DragEvent, KeyboardEvent } from 'react'
import { api } from '../api/client'
import { hasFileDrag, readFileDragPayload } from '../hooks/useDraggableFiles'

type FolderDropPanelProps = {
  folders: string[]
  onDropFiles: (folder: string, ids: number[]) => void
  onFolderCreated?: (path: string) => void
  rootPath?: string
  title?: string
  hint?: string
  disabled?: boolean
}

export function FolderDropPanel({
  folders,
  onDropFiles,
  onFolderCreated,
  rootPath,
  title = 'フォルダへドラッグして移動',
  hint = '画像をここへドラッグするとフォルダへ移動できます。',
  disabled,
}: FolderDropPanelProps) {
  const [overFolder, setOverFolder] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const filtered = filter
    ? folders.filter((f) => f.toLowerCase().includes(filter.toLowerCase()))
    : folders

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
      </header>
      <input
        type="search"
        className="input"
        placeholder="フォルダを検索..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        disabled={disabled}
      />
      <div className="folder-drop-list">
        {filtered.length === 0 && !creatingFolder && (
          <p className="muted">該当するフォルダがありません。</p>
        )}
        {filtered.map((folder) => (
          <div
            key={folder}
            className={`folder-drop-item drop-zone ${overFolder === folder ? 'over' : ''}`}
            onDragOver={handleDragOver(folder)}
            onDragEnter={handleDragOver(folder)}
            onDragLeave={handleDragLeave(folder)}
            onDrop={handleDrop(folder)}
            title={folder}
          >
            <span className="folder-drop-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 16 16">
                <path
                  d="M2 4.5A1.5 1.5 0 0 1 3.5 3H6l1.5 2H12.5A1.5 1.5 0 0 1 14 6.5V12a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12V4.5Z"
                  fill="currentColor"
                />
              </svg>
            </span>
            <span className="folder-drop-name mono">{folder}</span>
          </div>
        ))}
      </div>

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
    </aside>
  )
}

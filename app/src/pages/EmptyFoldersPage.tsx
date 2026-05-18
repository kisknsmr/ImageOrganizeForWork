import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function pickFolder(): Promise<string | null> {
  if (!isTauri) return null
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({ directory: true, multiple: false })
  if (typeof selected === 'string') return selected
  return null
}

export function EmptyFoldersPage() {
  const toast = useToast()
  const [root, setRoot] = useState('')
  const [folders, setFolders] = useState<string[] | null>(null)
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set())

  const scanMutation = useMutation({
    mutationFn: () => api.emptyFoldersScan(root),
    onSuccess: (data) => {
      setFolders(data.folders)
      setSelectedPaths(new Set(data.folders))
      if (data.count === 0) {
        toast.warning('空フォルダは見つかりませんでした。', 'Empty Folders')
      } else {
        toast.success(`空フォルダを ${data.count} 件検出しました`, 'Empty Folders')
      }
    },
    onError: (e) => toast.error(getApiErrorMessage(e), 'スキャンに失敗しました'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.emptyFoldersDelete(Array.from(selectedPaths)),
    onSuccess: (data) => {
      if (data.failed.length > 0) {
        toast.warning(`削除: ${data.deleted} 件 / 失敗: ${data.failed.length} 件`, 'Empty Folders')
      } else {
        toast.success(`${data.deleted} 件の空フォルダを削除しました`, 'Empty Folders')
      }
      setFolders(null)
      setSelectedPaths(new Set())
    },
    onError: (e) => toast.error(getApiErrorMessage(e), '削除に失敗しました'),
  })

  const toggleAll = () => {
    if (!folders) return
    setSelectedPaths((prev) =>
      prev.size === folders.length ? new Set() : new Set(folders)
    )
  }

  const toggle = (path: string) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  const busy = scanMutation.isPending || deleteMutation.isPending

  return (
    <section className="page">
      <header className="page-header">
        <h2>Empty Folders</h2>
        <p className="page-subtitle">指定フォルダ配下の空フォルダを検出して一括削除します。</p>
      </header>

      <article className="card" style={{ flexShrink: 0 }}>
        <div className="organize-form-row">
          <label className="label">対象フォルダ</label>
          <p className="muted" style={{ fontSize: 11, margin: '0 0 4px' }}>
            このフォルダ配下を再帰的にスキャンして空フォルダを検出します。
          </p>
          <div className="row">
            <input
              className="input"
              value={root}
              onChange={(e) => setRoot(e.target.value)}
              placeholder="例: D:/Pictures"
              disabled={busy}
            />
            {isTauri && (
              <button className="button ghost" type="button" disabled={busy}
                onClick={async () => { const p = await pickFolder(); if (p) setRoot(p) }}>
                参照...
              </button>
            )}
          </div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="button" type="button" disabled={!root || busy}
            onClick={() => { setFolders(null); scanMutation.mutate() }}>
            {scanMutation.isPending ? <Spinner size={14} inline /> : null}
            スキャン
          </button>
          <button className="button danger" type="button"
            disabled={selectedPaths.size === 0 || busy}
            onClick={() => deleteMutation.mutate()}>
            {deleteMutation.isPending ? <Spinner size={14} inline /> : null}
            選択した空フォルダを削除 ({selectedPaths.size})
          </button>
        </div>
      </article>

      {folders && folders.length > 0 && (
        <>
          <div className="toolbar" style={{ flexShrink: 0 }}>
            <div className="toolbar-group">
              <span className="status-chip">
                <span className="status-dot" />
                {folders.length} 件
              </span>
              <span className="muted">選択中: {selectedPaths.size}</span>
            </div>
            <div className="toolbar-group">
              <button className="button ghost" onClick={toggleAll} disabled={busy}>
                {selectedPaths.size === folders.length ? '全解除' : '全選択'}
              </button>
            </div>
          </div>
          <div className="pane-scroll">
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ position: 'sticky', top: 0, background: '#111928', zIndex: 1 }}>
                  <th style={{ width: 40, padding: '6px 8px' }} />
                  <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 600 }}>フォルダパス</th>
                </tr>
              </thead>
              <tbody>
                {folders.map((path) => (
                  <tr key={path}
                    onClick={() => toggle(path)}
                    className="selectable"
                    style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}
                  >
                    <td style={{ padding: '5px 8px', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={selectedPaths.has(path)}
                        onChange={() => toggle(path)}
                        onClick={(e) => e.stopPropagation()}
                        disabled={busy}
                      />
                    </td>
                    <td style={{ padding: '5px 8px', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                      {path}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {folders && folders.length === 0 && (
        <article className="card" style={{ textAlign: 'center', padding: 32, flexShrink: 0 }}>
          <p className="muted">空フォルダは見つかりませんでした。</p>
        </article>
      )}

      {!folders && !scanMutation.isPending && (
        <article className="card" style={{ textAlign: 'center', padding: 32, flexShrink: 0 }}>
          <p className="muted">対象フォルダを指定して「スキャン」を押してください。</p>
        </article>
      )}
    </section>
  )
}

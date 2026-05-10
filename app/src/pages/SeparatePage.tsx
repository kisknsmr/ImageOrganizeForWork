import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'
import type { SeparateItem } from '../types'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function pickFolder(): Promise<string | null> {
  if (!isTauri) return null
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({ directory: true, multiple: false })
  if (typeof selected === 'string') return selected
  return null
}

function FolderInput({
  label, description, value, onChange, disabled,
}: {
  label: string; description: string; value: string; onChange: (v: string) => void; disabled: boolean
}) {
  return (
    <div className="organize-form-row">
      <label className="label">{label}</label>
      <p className="muted" style={{ fontSize: 11, margin: '0 0 4px' }}>{description}</p>
      <div className="row">
        <input className="input" value={value} onChange={(e) => onChange(e.target.value)}
          placeholder="例: D:/Pictures/sorted" disabled={disabled} />
        {isTauri && (
          <button className="button ghost" type="button" disabled={disabled}
            onClick={async () => { const p = await pickFolder(); if (p) onChange(p) }}>
            参照...
          </button>
        )}
      </div>
    </div>
  )
}

type PreviewTableProps = {
  items: SeparateItem[]
  filter: 'all' | 'image' | 'video'
}

function PreviewTable({ items, filter }: PreviewTableProps) {
  const filtered = filter === 'all' ? items : items.filter((i) => i.kind === filter)
  return (
    <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ position: 'sticky', top: 0, background: '#111928', zIndex: 1 }}>
            <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 600, width: 60 }}>種別</th>
            <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 600 }}>相対パス（移動元）</th>
            <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 600 }}>移動先</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((item, i) => (
            <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '5px 8px' }}>
                <span style={{
                  display: 'inline-block', padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                  background: item.kind === 'image' ? 'rgba(79,140,255,0.2)' : 'rgba(167,139,250,0.2)',
                  color: item.kind === 'image' ? '#79a8ff' : '#c4b5fd',
                }}>
                  {item.kind === 'image' ? '画像' : '動画'}
                </span>
              </td>
              <td style={{ padding: '5px 8px', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                {item.rel_path}
              </td>
              <td style={{ padding: '5px 8px', color: 'var(--text-muted)', wordBreak: 'break-all', fontSize: 11 }}>
                {item.dst}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SeparatePage() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [sourceRoot, setSourceRoot] = useState('')
  const [imageDest, setImageDest] = useState('')
  const [videoDest, setVideoDest] = useState('')
  const [preview, setPreview] = useState<SeparateItem[] | null>(null)
  const [filter, setFilter] = useState<'all' | 'image' | 'video'>('all')
  const [applying, setApplying] = useState(false)

  const undoStatus = useQuery({
    queryKey: ['separate-undo-status'],
    queryFn: api.separateUndoStatus,
    refetchInterval: 2000,
  })

  // 進捗ポーリング（実行中のみ）
  const progress = useQuery({
    queryKey: ['separate-progress'],
    queryFn: api.separateProgress,
    refetchInterval: 500,
    enabled: applying,
  })

  // 完了検知
  if (applying && progress.data?.finished) {
    setApplying(false)
    setPreview(null)
    const d = progress.data
    toast.success(`${d.moved} 件を移動しました`, 'Separate')
    if (d.failed_count > 0) toast.warning(`${d.failed_count} 件の移動に失敗しました`, 'Separate')
    queryClient.invalidateQueries({ queryKey: ['separate-undo-status'] })
  }

  const previewMutation = useMutation({
    mutationFn: () => api.separatePreview({ source_root: sourceRoot, image_dest: imageDest, video_dest: videoDest }),
    onSuccess: (data) => {
      setPreview(data.items)
      setFilter('all')
      toast.success(`画像 ${data.image_count} 件・動画 ${data.video_count} 件を検出しました`, 'Separate')
    },
    onError: (e) => toast.error(getApiErrorMessage(e), 'プレビューに失敗しました'),
  })

  const applyMutation = useMutation({
    mutationFn: () => api.separateApply(preview!),
    onSuccess: (data) => {
      if (data.started) {
        setApplying(true)
      } else {
        toast.warning(data.message ?? '開始できませんでした', 'Separate')
      }
    },
    onError: (e) => toast.error(getApiErrorMessage(e), '移動に失敗しました'),
  })

  const undoMutation = useMutation({
    mutationFn: api.separateUndo,
    onSuccess: (data) => {
      if (data.ok) toast.success(`${data.restored ?? 0} 件を元に戻しました`, 'Undo')
      else toast.warning(data.message ?? 'Undo できませんでした', 'Undo')
      queryClient.invalidateQueries({ queryKey: ['separate-undo-status'] })
    },
    onError: (e) => toast.error(getApiErrorMessage(e), 'Undo に失敗しました'),
  })

  const busy = previewMutation.isPending || applyMutation.isPending || applying
  const imageCount = preview?.filter((i) => i.kind === 'image').length ?? 0
  const videoCount = preview?.filter((i) => i.kind === 'video').length ?? 0
  const canPreview = !!sourceRoot && !!imageDest && !!videoDest
  const prog = progress.data

  return (
    <section className="page">
      <header className="page-header">
        <h2>Separate</h2>
        <p className="page-subtitle">
          フォルダ構造を保ったまま、画像と動画を別々の出力先フォルダへ分離します。
        </p>
      </header>

      {/* 設定 */}
      <article className="card" style={{ flexShrink: 0 }}>
        <div className="organize-form">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
            <FolderInput
              label="分離対象フォルダ"
              description="この中のファイルを画像と動画に分けます"
              value={sourceRoot} onChange={setSourceRoot} disabled={busy}
            />
            <FolderInput
              label="画像の出力先"
              description="画像ファイルはここに移動されます"
              value={imageDest} onChange={setImageDest} disabled={busy}
            />
            <FolderInput
              label="動画の出力先"
              description="動画ファイルはここに移動されます"
              value={videoDest} onChange={setVideoDest} disabled={busy}
            />
          </div>
          <div className="row" style={{ marginTop: 4 }}>
            <button className="button" type="button" disabled={!canPreview || busy}
              onClick={() => previewMutation.mutate()}>
              {previewMutation.isPending ? <Spinner size={14} inline /> : null}
              プレビュー
            </button>
            <button className="button danger" type="button"
              disabled={!preview || preview.length === 0 || busy}
              onClick={() => applyMutation.mutate()}>
              {applyMutation.isPending ? <Spinner size={14} inline /> : null}
              確定して移動する
            </button>
            {undoStatus.data?.can_undo && (
              <button className="button ghost" type="button" disabled={undoMutation.isPending}
                onClick={() => undoMutation.mutate()}>
                {undoMutation.isPending ? <Spinner size={14} inline /> : null}
                Undo（直前の移動を取り消す）
              </button>
            )}
            {preview && (
              <button className="button ghost" type="button" disabled={busy}
                onClick={() => setPreview(null)}>
                キャンセル
              </button>
            )}
          </div>
        </div>
      </article>

      {/* 実行中プログレス */}
      {applying && prog && (
        <article className="card" style={{ flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>移動中...</span>
            <span className="muted" style={{ fontSize: 12 }}>
              {prog.done} / {prog.total} 件（{prog.percent}%）
            </span>
          </div>
          <progress value={prog.percent} max={100} />
          <div className="row" style={{ marginTop: 8, gap: 16 }}>
            <span style={{ fontSize: 12, color: '#79a8ff' }}>移動済み: {prog.moved}</span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>スキップ: {prog.skipped}</span>
            {prog.failed_count > 0 && (
              <span style={{ fontSize: 12, color: 'var(--danger)' }}>失敗: {prog.failed_count}</span>
            )}
          </div>
        </article>
      )}

      {/* プレビューテーブル */}
      {preview && !applying && (
        <>
          <div className="toolbar" style={{ flexShrink: 0 }}>
            <div className="toolbar-group">
              <span className="status-chip">
                <span className="status-dot" />
                合計 {preview.length} 件
              </span>
              <span style={{ fontSize: 12, color: '#79a8ff' }}>画像 {imageCount} 件</span>
              <span style={{ fontSize: 12, color: '#c4b5fd' }}>動画 {videoCount} 件</span>
            </div>
            <div className="toolbar-group">
              {(['all', 'image', 'video'] as const).map((f) => (
                <button key={f} className={`button ${filter === f ? '' : 'ghost'}`}
                  onClick={() => setFilter(f)} style={{ padding: '4px 10px', fontSize: 12 }}>
                  {f === 'all' ? 'すべて' : f === 'image' ? '画像のみ' : '動画のみ'}
                </button>
              ))}
            </div>
          </div>
          <div className="pane-scroll">
            <PreviewTable items={preview} filter={filter} />
          </div>
        </>
      )}

      {!preview && !previewMutation.isPending && (
        <article className="card" style={{ textAlign: 'center', padding: 32, flexShrink: 0 }}>
          <p className="muted">
            3つのフォルダを指定して「プレビュー」を押すと、移動予定の一覧が表示されます。<br />
            内容を確認してから「確定して移動する」で実行してください。
          </p>
        </article>
      )}
    </section>
  )
}

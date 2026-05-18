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

type KindFilter = 'all' | 'image' | 'video' | 'audio' | 'other'

const KIND_LABEL: Record<string, string> = {
  image: '画像',
  video: '動画',
  audio: '音声',
  other: 'その他',
}

const KIND_COLOR: Record<string, { bg: string; text: string }> = {
  image: { bg: 'rgba(79,140,255,0.2)', text: '#79a8ff' },
  video: { bg: 'rgba(167,139,250,0.2)', text: '#c4b5fd' },
  audio: { bg: 'rgba(52,211,153,0.2)', text: '#6ee7b7' },
  other: { bg: 'rgba(156,163,175,0.2)', text: '#9ca3af' },
}

const DEST_FOLDER_KEY: Record<string, string> = {
  image: '01_picture',
  video: '02_movie',
  audio: '03_sound',
  other: '04_others',
}

function PreviewTable({ items, filter }: { items: SeparateItem[]; filter: KindFilter }) {
  const filtered = filter === 'all' ? items : items.filter((i) => i.kind === filter)
  return (
    <div style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ position: 'sticky', top: 0, background: '#111928', zIndex: 1 }}>
            <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 600, width: 60 }}>種別</th>
            <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 600 }}>相対パス（移動元）</th>
            <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 600 }}>移動先フォルダ</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((item, i) => {
            const c = KIND_COLOR[item.kind] ?? KIND_COLOR.other
            return (
              <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '5px 8px' }}>
                  <span style={{
                    display: 'inline-block', padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                    background: c.bg, color: c.text,
                  }}>
                    {KIND_LABEL[item.kind] ?? item.kind}
                  </span>
                </td>
                <td style={{ padding: '5px 8px', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                  {item.rel_path}
                </td>
                <td style={{ padding: '5px 8px', color: 'var(--text-muted)', wordBreak: 'break-all', fontSize: 11 }}>
                  {DEST_FOLDER_KEY[item.kind] ?? 'others'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

type PreviewResult = {
  items: SeparateItem[]
  image_count: number
  video_count: number
  audio_count: number
  other_count: number
  dest_folders: Record<string, string>
}

export function SeparatePage() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [sourceRoot, setSourceRoot] = useState('')
  const [previewData, setPreviewData] = useState<PreviewResult | null>(null)
  const [filter, setFilter] = useState<KindFilter>('all')
  const [applying, setApplying] = useState(false)

  const undoStatus = useQuery({
    queryKey: ['separate-undo-status'],
    queryFn: api.separateUndoStatus,
    refetchInterval: 2000,
  })

  const progress = useQuery({
    queryKey: ['separate-progress'],
    queryFn: api.separateProgress,
    refetchInterval: 500,
    enabled: applying,
  })

  if (applying && progress.data?.finished) {
    setApplying(false)
    setPreviewData(null)
    const d = progress.data
    toast.success(`${d.moved} 件を移動しました`, 'Separate')
    if (d.failed_count > 0) toast.warning(`${d.failed_count} 件の移動に失敗しました`, 'Separate')
    queryClient.invalidateQueries({ queryKey: ['separate-undo-status'] })
  }

  const previewMutation = useMutation({
    mutationFn: () => api.separatePreview({ source_root: sourceRoot }),
    onSuccess: (data) => {
      if (data.items.length === 0) {
        toast.warning('対象ファイルが見つかりませんでした。フォルダにファイルが存在するか確認してください。', 'Separate')
        return
      }
      setPreviewData(data)
      setFilter('all')
      const parts = [
        data.image_count > 0 ? `画像 ${data.image_count} 件` : '',
        data.video_count > 0 ? `動画 ${data.video_count} 件` : '',
        data.audio_count > 0 ? `音声 ${data.audio_count} 件` : '',
        data.other_count > 0 ? `その他 ${data.other_count} 件` : '',
      ].filter(Boolean).join('・')
      toast.success(`${parts} を検出しました`, 'Separate')
    },
    onError: (e) => toast.error(getApiErrorMessage(e), 'プレビューに失敗しました'),
  })

  const applyMutation = useMutation({
    mutationFn: () => api.separateApply(previewData!.items),
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
  const preview = previewData?.items ?? null
  const prog = progress.data

  const FILTER_BUTTONS: { key: KindFilter; label: string }[] = [
    { key: 'all', label: 'すべて' },
    { key: 'image', label: '画像のみ' },
    { key: 'video', label: '動画のみ' },
    { key: 'audio', label: '音声のみ' },
    { key: 'other', label: 'その他のみ' },
  ]

  return (
    <section className="page">
      <header className="page-header">
        <h2>Separate</h2>
        <p className="page-subtitle">
          対象フォルダを指定すると、同じ階層に <code>01_picture</code> / <code>02_movie</code> / <code>03_sound</code> / <code>04_others</code> フォルダを作成してファイルを移動します。
        </p>
      </header>

      {/* 設定 */}
      <article className="card" style={{ flexShrink: 0 }}>
        <div className="organize-form">
          <div className="organize-form-row">
            <label className="label">分離対象フォルダ</label>
            <p className="muted" style={{ fontSize: 11, margin: '0 0 4px' }}>
              このフォルダの中身を種別に分けます。親フォルダ内に出力先フォルダが自動作成されます。
            </p>
            <div className="row">
              <input
                className="input"
                value={sourceRoot}
                onChange={(e) => setSourceRoot(e.target.value)}
                placeholder="例: D:/Pictures/raw"
                disabled={busy}
              />
              {isTauri && (
                <button className="button ghost" type="button" disabled={busy}
                  onClick={async () => { const p = await pickFolder(); if (p) setSourceRoot(p) }}>
                  参照...
                </button>
              )}
            </div>
          </div>

          {/* 出力先フォルダのプレビュー表示 */}
          {sourceRoot && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginTop: 8 }}>
              {(['image', 'video', 'audio', 'other'] as const).map((kind) => {
                const c = KIND_COLOR[kind]
                const folderName = DEST_FOLDER_KEY[kind]
                return (
                  <div key={kind} style={{
                    padding: '8px 12px', borderRadius: 6, border: `1px solid ${c.bg}`,
                    background: c.bg, fontSize: 12,
                  }}>
                    <span style={{ fontWeight: 700, color: c.text }}>{KIND_LABEL[kind]}</span>
                    <p style={{ margin: '2px 0 0', color: 'var(--text-muted)', fontSize: 11, wordBreak: 'break-all' }}>
                      → …/{folderName}/
                    </p>
                  </div>
                )
              })}
            </div>
          )}

          <div className="row" style={{ marginTop: 12 }}>
            <button className="button" type="button" disabled={!sourceRoot || busy}
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
                onClick={() => setPreviewData(null)}>
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
              {((['image', 'video', 'audio', 'other'] as const)).map((kind) => {
                const count = preview.filter((i) => i.kind === kind).length
                if (!count) return null
                return (
                  <span key={kind} style={{ fontSize: 12, color: KIND_COLOR[kind].text }}>
                    {KIND_LABEL[kind]} {count} 件
                  </span>
                )
              })}
            </div>
            <div className="toolbar-group">
              {FILTER_BUTTONS.map((f) => (
                <button key={f.key} className={`button ${filter === f.key ? '' : 'ghost'}`}
                  onClick={() => setFilter(f.key)} style={{ padding: '4px 10px', fontSize: 12 }}>
                  {f.label}
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
            対象フォルダを指定して「プレビュー」を押すと、移動予定の一覧が表示されます。<br />
            内容を確認してから「確定して移動する」で実行してください。
          </p>
        </article>
      )}
    </section>
  )
}

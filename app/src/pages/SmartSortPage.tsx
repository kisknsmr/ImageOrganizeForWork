import { ThumbnailImg } from '../components/ThumbnailImg'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'
import type { OrganizeSuggestion } from '../types'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function pickFolder(): Promise<string | null> {
  if (!isTauri) return null
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({ directory: true, multiple: false })
  if (typeof selected === 'string') return selected
  return null
}

function formatDate(iso: string) {
  if (!iso) return ''
  return iso.slice(0, 10)
}

function GroupCard({
  suggestion,
  selected,
  onClick,
}: {
  suggestion: OrganizeSuggestion
  selected: boolean
  onClick: () => void
}) {
  const repItems = suggestion.items.filter((i) => i.is_representative)
  const firstRep = repItems[0]
  return (
    <button
      className={`group-picker-item card selectable ${selected ? 'selected' : ''}`}
      onClick={onClick}
      style={{ width: '100%' }}
    >
      {firstRep && (
        <img
          src={api.thumbnailUrl(firstRep.id)}
          alt={firstRep.filename}
          className="group-picker-thumb"
          loading="lazy"
        />
      )}
      <div className="group-picker-info">
        <p style={{ margin: 0, fontWeight: 700, fontSize: 13 }}>{suggestion.suggested_name}</p>
        <p className="muted" style={{ fontSize: 11, margin: '2px 0 0' }}>
          {suggestion.items.length} 枚 · {formatDate(suggestion.date_range.start)}
          {suggestion.date_range.start !== suggestion.date_range.end
            ? ` 〜 ${formatDate(suggestion.date_range.end)}`
            : ''}
        </p>
        <p className="muted" style={{ fontSize: 10, margin: '2px 0 0' }}>{suggestion.reason}</p>
      </div>
    </button>
  )
}

export function SmartSortPage() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [targetPath, setTargetPath] = useState('')
  const [destRoot, setDestRoot] = useState('')
  const [timeGap, setTimeGap] = useState(4)
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.25)
  const [suggestions, setSuggestions] = useState<OrganizeSuggestion[]>([])
  const [editedNames, setEditedNames] = useState<Record<string, string>>({})
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null)

  const undoStatus = useQuery({
    queryKey: ['organize-undo-status'],
    queryFn: api.organizeUndoStatus,
    refetchInterval: 2000,
  })

  const suggestMutation = useMutation({
    mutationFn: () =>
      api.organizeSuggest({
        target_path: targetPath,
        destination_root: destRoot,
        config: { time_gap_hours: timeGap, confidence_threshold: confidenceThreshold },
      }),
    onSuccess: (data) => {
      setSuggestions(data.suggestions)
      setEditedNames({})
      setSelectedGroupId(data.suggestions[0]?.group_id ?? null)
      if (data.message) toast.info(data.message, 'Smart Sort')
      else toast.success(`${data.suggestions.length} グループの提案を生成しました`, 'Smart Sort')
    },
    onError: (e) => toast.error(getApiErrorMessage(e), '提案生成に失敗しました'),
  })

  const applyMutation = useMutation({
    mutationFn: () =>
      api.organizeApply({
        destination_root: destRoot,
        plan: suggestions.map((s) => ({
          group_id: s.group_id,
          suggested_name: editedNames[s.group_id] ?? s.suggested_name,
          items: s.items.map((i) => ({ path: i.path })),
        })),
      }),
    onSuccess: (data) => {
      toast.success(`${data.moved} 件を移動しました`, 'Smart Sort')
      if (data.failed.length > 0) toast.warning(`${data.failed.length} 件の移動に失敗しました`, 'Smart Sort')
      setSuggestions([])
      setSelectedGroupId(null)
      queryClient.invalidateQueries({ queryKey: ['organize-undo-status'] })
    },
    onError: (e) => toast.error(getApiErrorMessage(e), '適用に失敗しました'),
  })

  const undoMutation = useMutation({
    mutationFn: api.organizeUndo,
    onSuccess: (data) => {
      if (data.ok) {
        toast.success(`${data.restored ?? 0} 件を元に戻しました`, 'Undo')
      } else {
        toast.warning(data.message ?? 'Undo できませんでした', 'Undo')
      }
      queryClient.invalidateQueries({ queryKey: ['organize-undo-status'] })
    },
    onError: (e) => toast.error(getApiErrorMessage(e), 'Undo に失敗しました'),
  })

  const busy = suggestMutation.isPending || applyMutation.isPending
  const selectedGroup = suggestions.find((s) => s.group_id === selectedGroupId) ?? null

  return (
    <section className="page">
      <header className="page-header">
        <h2>Smart Sort</h2>
        <p className="page-subtitle">
          撮影日時と CLIP（ローカルAI）による内容解析でフォルダ仕分けを提案します。確認・編集後に適用してください。
        </p>
      </header>

      {/* 設定カード */}
      <article className="card">
        <h3 className="section-title" style={{ marginBottom: 12 }}>設定</h3>
        <div className="organize-form">
          <div className="organize-form-row">
            <label className="label">整理対象フォルダ</label>
            <div className="row">
              <input
                className="input"
                value={targetPath}
                onChange={(e) => setTargetPath(e.target.value)}
                placeholder="D:/Pictures/Import"
                disabled={busy}
              />
              {isTauri && (
                <button className="button ghost" type="button" disabled={busy}
                  onClick={async () => { const p = await pickFolder(); if (p) setTargetPath(p) }}>
                  参照...
                </button>
              )}
            </div>
          </div>
          <div className="organize-form-row">
            <label className="label">出力先フォルダ（整理後のファイルを移動）</label>
            <div className="row">
              <input
                className="input"
                value={destRoot}
                onChange={(e) => setDestRoot(e.target.value)}
                placeholder="D:/Pictures/Sorted"
                disabled={busy}
              />
              {isTauri && (
                <button className="button ghost" type="button" disabled={busy}
                  onClick={async () => { const p = await pickFolder(); if (p) setDestRoot(p) }}>
                  参照...
                </button>
              )}
            </div>
          </div>
          <div className="organize-form-row organize-form-row--inline">
            <label className="label" style={{ minWidth: 200 }}>
              時間ギャップ（グループ分割の閾値）: {timeGap}時間
            </label>
            <input type="range" min={1} max={24} value={timeGap}
              onChange={(e) => setTimeGap(Number(e.target.value))} style={{ width: 160 }} />
          </div>
          <div className="organize-form-row organize-form-row--inline">
            <label className="label" style={{ minWidth: 200 }}>
              信頼度閾値: {confidenceThreshold.toFixed(2)}
            </label>
            <input type="range" min={0.05} max={0.9} step={0.05} value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(Number(e.target.value))} style={{ width: 160 }} />
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button
              className="button"
              type="button"
              disabled={!targetPath || !destRoot || busy}
              onClick={() => suggestMutation.mutate()}
            >
              {suggestMutation.isPending ? <Spinner size={14} inline /> : null}
              提案を生成
            </button>
            {undoStatus.data?.can_undo && (
              <button
                className="button ghost"
                type="button"
                disabled={undoMutation.isPending}
                onClick={() => undoMutation.mutate()}
              >
                {undoMutation.isPending ? <Spinner size={14} inline /> : null}
                Undo（直前の移動を取り消す）
              </button>
            )}
          </div>
        </div>
      </article>

      {/* 提案プレビュー */}
      {suggestions.length > 0 && (
        <>
          <div className="toolbar">
            <div className="toolbar-group">
              <span className="status-chip">
                <span className="status-dot" />
                {suggestions.length} グループ · {suggestions.reduce((s, g) => s + g.items.length, 0)} 枚
              </span>
            </div>
            <div className="toolbar-group">
              <button
                className="button danger"
                type="button"
                disabled={busy}
                onClick={() => applyMutation.mutate()}
              >
                {applyMutation.isPending ? <Spinner size={14} inline /> : null}
                確定して移動する
              </button>
              <button
                className="button ghost"
                type="button"
                disabled={busy}
                onClick={() => { setSuggestions([]); setSelectedGroupId(null) }}
              >
                キャンセル
              </button>
            </div>
          </div>

          {/* 2ペイン: グループ一覧 | 写真グリッド */}
          <div className="gallery-layout" style={{ gridTemplateColumns: 'minmax(240px, 26vw) 1fr', flex: 1, minHeight: 0 }}>
            <div style={{ overflowY: 'auto', minHeight: 0 }}>
              <p className="pane-heading muted">提案グループ</p>
              <div className="group-picker-list">
                {suggestions.map((s) => (
                  <GroupCard
                    key={s.group_id}
                    suggestion={s}
                    selected={selectedGroupId === s.group_id}
                    onClick={() => setSelectedGroupId(s.group_id)}
                  />
                ))}
              </div>
            </div>

            <aside className="preview-pane" style={{ overflowY: 'auto', minHeight: 0 }}>
              {!selectedGroup && <p className="muted">左からグループを選択してください。</p>}
              {selectedGroup && (
                <>
                  <div style={{ marginBottom: 12 }}>
                    <label className="label" style={{ display: 'block', marginBottom: 4 }}>
                      フォルダ名（編集可）
                    </label>
                    <input
                      className="input"
                      value={editedNames[selectedGroup.group_id] ?? selectedGroup.suggested_name}
                      onChange={(e) =>
                        setEditedNames((prev) => ({ ...prev, [selectedGroup.group_id]: e.target.value }))
                      }
                      style={{ maxWidth: 400 }}
                    />
                    <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                      {formatDate(selectedGroup.date_range.start)} 〜 {formatDate(selectedGroup.date_range.end)} ·{' '}
                      {selectedGroup.items.length} 枚 · {selectedGroup.reason}
                    </p>
                  </div>
                  <div className="thumb-grid" style={{ ['--thumb-size' as string]: '120px' } as React.CSSProperties}>
                    {selectedGroup.items.map((item) => (
                      <div
                        key={item.id}
                        className={`thumb-item ${item.is_representative ? 'best-shot' : ''}`}
                        title={item.filename}
                      >
                        <ThumbnailImg src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
                        {item.is_representative && <span className="best-badge">代表</span>}
                        <span>{item.filename}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </aside>
          </div>
        </>
      )}

      {suggestions.length === 0 && !suggestMutation.isPending && (
        <article className="card" style={{ textAlign: 'center', padding: 32 }}>
          <p className="muted">
            整理対象フォルダと出力先フォルダを指定して「提案を生成」を押してください。<br />
            ※ 事前にスキャンと解析が完了しているファイルのみが対象です。
          </p>
        </article>
      )}
    </section>
  )
}

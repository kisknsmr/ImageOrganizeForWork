import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'
import type { OrganizeGroup } from '../types'

const PREVIEW_THUMBS = 8

function formatRange(group: OrganizeGroup): string {
  if (!group.start_time) return '日付不明'
  const start = group.start_time.slice(0, 10)
  const end = group.end_time?.slice(0, 10) ?? start
  return start === end ? start : `${start} 〜 ${end}`
}

export function AiOrganizePage() {
  const toast = useToast()
  const [gapHours, setGapHours] = useState(6)
  const [minGroupSize, setMinGroupSize] = useState(2)
  // null = 未編集。名前・選択・整理先はユーザーが触った分だけ上書きし、既定値はデータから導出する
  const [destinationInput, setDestinationInput] = useState<string | null>(null)
  const [names, setNames] = useState<Record<string, string>>({})
  const [included, setIncluded] = useState<Record<string, boolean>>({})

  const capabilities = useQuery({
    queryKey: ['organize-capabilities'],
    queryFn: api.organizeCapabilities,
  })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const preview = useQuery({
    queryKey: ['organize-preview', gapHours, minGroupSize],
    queryFn: () => api.organizePreview(gapHours, minGroupSize, PREVIEW_THUMBS),
  })

  const groups = useMemo(() => preview.data?.groups ?? [], [preview.data])

  // 日付不明グループは既定で除外。ユーザーの操作分（included）だけ上書き
  const isIncluded = (group: OrganizeGroup) => included[group.id] ?? group.start_time != null
  // 整理先の既定値: ライブラリルート直下の「整理済み」
  const destinationRoot =
    destinationInput ?? (settings.data?.root_path ? `${settings.data.root_path}\\整理済み` : '')

  const selectedGroups = groups.filter(isIncluded)
  const selectedFileCount = selectedGroups.reduce((sum, group) => sum + group.count, 0)

  const applyMutation = useMutation({
    mutationFn: () =>
      api.organizeApply(
        destinationRoot.trim(),
        selectedGroups.map((group) => ({
          name: (names[group.id] ?? group.suggested_name).trim() || group.suggested_name,
          file_ids: group.file_ids,
        })),
      ),
    onSuccess: async (res) => {
      const failed = res.failed_ids?.length ?? 0
      if (failed > 0) {
        toast.warning(`移動: ${res.moved} 件 / 失敗: ${failed} 件`, 'Smart organize')
      } else {
        toast.success(`${res.moved} 件を ${res.folders.length} フォルダへ整理しました`, 'Smart organize')
      }
      setNames({})
      setIncluded({})
      await preview.refetch()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '整理の適用に失敗しました')
    },
  })

  const apply = () => {
    if (!selectedGroups.length || applyMutation.isPending) return
    if (!destinationRoot.trim()) {
      toast.warning('整理先フォルダを入力してください', 'Smart organize')
      return
    }
    const message =
      `${selectedGroups.length} グループ（${selectedFileCount} 件）を\n` +
      `${destinationRoot.trim()}\n配下のイベント別フォルダへ移動します。よろしいですか？`
    if (!window.confirm(message)) return
    applyMutation.mutate()
  }

  const setAll = (value: boolean) => {
    setIncluded(Object.fromEntries(groups.map((group) => [group.id, value])))
  }

  const busy = applyMutation.isPending
  const aiReady = capabilities.data?.content ?? false

  return (
    <section className="page">
      <header className="page-header">
        <h2>Smart Organize</h2>
        <p className="page-subtitle">
          撮影時刻の間隔からイベント（旅行・撮影会など）を推定し、イベントごとのフォルダへまとめて整理します。
        </p>
      </header>

      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            {groups.length} groups
          </span>
          <label className="muted">
            イベント間隔(時間):
            <input
              className="input"
              type="number"
              min={1}
              max={168}
              value={gapHours}
              onChange={(e) => setGapHours(Math.min(168, Math.max(1, Number(e.target.value) || 1)))}
              disabled={busy}
              style={{ width: 72, marginLeft: 8 }}
            />
          </label>
          <label className="muted">
            最小枚数:
            <input
              className="input"
              type="number"
              min={1}
              max={1000}
              value={minGroupSize}
              onChange={(e) => setMinGroupSize(Math.min(1000, Math.max(1, Number(e.target.value) || 1)))}
              disabled={busy}
              style={{ width: 64, marginLeft: 8 }}
            />
          </label>
        </div>
        <div className="toolbar-group">
          <button className="button secondary" type="button" disabled={busy} onClick={() => setAll(true)}>
            すべて選択
          </button>
          <button className="button secondary" type="button" disabled={busy} onClick={() => setAll(false)}>
            選択解除
          </button>
          <button
            className="button"
            type="button"
            disabled={busy || !selectedGroups.length}
            onClick={apply}
          >
            {busy ? <Spinner size={14} inline /> : null}
            整理を実行 ({selectedGroups.length} グループ / {selectedFileCount} 件)
          </button>
        </div>
      </div>

      <div className="toolbar">
        <div className="toolbar-group" style={{ flex: 1 }}>
          <label className="muted" style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
            整理先:
            <input
              className="input"
              type="text"
              value={destinationRoot}
              onChange={(e) => setDestinationInput(e.target.value)}
              placeholder={settings.data?.root_path ? `${settings.data.root_path}\\整理済み` : '整理先フォルダの絶対パス'}
              disabled={busy}
              style={{ flex: 1, marginLeft: 8 }}
            />
          </label>
        </div>
      </div>

      {capabilities.isSuccess && !aiReady && (
        <article className="card">
          <p className="muted">
            現在は撮影時刻ベースのグルーピングのみ利用できます。CLIP による内容ベースの分類
            {capabilities.data?.ai_dependencies_installed
              ? 'はデスクトップ版（PyQt）でのみ利用可能です。'
              : 'を使う場合は AI 依存（torch / transformers）の導入が必要です（AI_SETUP_GUIDE.md 参照）。'}
          </p>
        </article>
      )}

      <QueryState
        isLoading={preview.isPending}
        isError={preview.isError}
        error={preview.error}
        isEmpty={!preview.isPending && !preview.isError && groups.length === 0}
        loadingMessage="イベントグループを作成中..."
        emptyMessage="グループ化できるファイルがありません。先に Import & Analyze を実行してください。"
      />

      {!preview.isPending && !preview.isError && (
        <div className="list-grid">
          {groups.map((group) => (
            <article key={group.id} className={`card ${isIncluded(group) ? 'selected' : ''}`}>
              <div className="toolbar-group" style={{ justifyContent: 'space-between', width: '100%' }}>
                <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={isIncluded(group)}
                    onChange={(e) => setIncluded((prev) => ({ ...prev, [group.id]: e.target.checked }))}
                    disabled={busy}
                  />
                  {formatRange(group)}
                </label>
                <span className="status-chip">{group.count} 件</span>
              </div>
              <input
                className="input"
                type="text"
                value={names[group.id] ?? group.suggested_name}
                onChange={(e) => setNames((prev) => ({ ...prev, [group.id]: e.target.value }))}
                disabled={busy}
                aria-label="フォルダ名"
                style={{ width: '100%', marginTop: 8 }}
              />
              <div className="thumb-grid" style={{ ['--thumb-size' as string]: '84px', marginTop: 10 } as React.CSSProperties}>
                {group.items.map((item) => (
                  <span key={item.id} className="thumb-item" title={item.filename}>
                    <img src={api.thumbnailUrl(item.id)} alt={item.filename} loading="lazy" />
                  </span>
                ))}
                {group.count > group.items.length && (
                  <span className="muted" style={{ alignSelf: 'center' }}>
                    +{group.count - group.items.length}
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

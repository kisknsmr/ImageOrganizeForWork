import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { QueryState } from '../components/QueryState'
import { Spinner } from '../components/Spinner'
import { getApiErrorMessage, useToast } from '../components/useToast'

function SettingRow({
  label,
  description,
  value,
  onChange,
  onSave,
  saving,
  type = 'text',
  min,
  max,
}: {
  label: string
  description: string
  value: string
  onChange: (v: string) => void
  onSave: () => void
  saving: boolean
  type?: string
  min?: number
  max?: number
}) {
  return (
    <div className="setting-row">
      <div className="setting-info">
        <p className="setting-label">{label}</p>
        <p className="muted setting-desc">{description}</p>
      </div>
      <div className="row" style={{ gap: 8 }}>
        <input
          type={type}
          className="input"
          value={value}
          min={min}
          max={max}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSave()}
          style={{ width: type === 'number' ? 100 : 320 }}
          disabled={saving}
        />
        <button className="button ghost" onClick={onSave} disabled={saving}>
          {saving ? <Spinner size={14} inline /> : '保存'}
        </button>
      </div>
    </div>
  )
}

export function SettingsPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats })

  const [rootPath, setRootPath] = useState('')
  const [retentionDays, setRetentionDays] = useState('')
  const [blurThreshold, setBlurThreshold] = useState('')
  const [simThreshold, setSimThreshold] = useState('')
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<'reset-analysis' | 'clear-all' | null>(null)

  useEffect(() => {
    if (!settings.data) return
    setRootPath(settings.data.root_path ?? '')
    setRetentionDays(settings.data.trash_retention_days ?? '14')
    setBlurThreshold(settings.data.blur_threshold ?? '20')
    setSimThreshold(settings.data.similarity_threshold ?? '5')
  }, [settings.data])

  const saveMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api.saveSetting(key, value),
    onSuccess: (_, vars) => {
      toast.success(`${vars.key} を保存しました`, 'Settings')
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      setSavingKey(null)
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '保存に失敗しました')
      setSavingKey(null)
    },
  })

  const resetAnalysisMutation = useMutation({
    mutationFn: api.dbResetAnalysis,
    onSuccess: (data) => {
      toast.success(`${data.reset} 件を未解析状態にリセットしました。再解析を実行してください。`, 'DB')
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      setConfirmAction(null)
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'リセットに失敗しました')
      setConfirmAction(null)
    },
  })

  const clearAllMutation = useMutation({
    mutationFn: api.dbClearAll,
    onSuccess: (data) => {
      toast.success(`${data.cleared} 件のレコードを全消去しました。スキャンからやり直してください。`, 'DB')
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      setConfirmAction(null)
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), 'クリアに失敗しました')
      setConfirmAction(null)
    },
  })

  const save = (key: string, value: string) => {
    setSavingKey(key)
    saveMutation.mutate({ key, value })
  }

  return (
    <section className="page">
      <header className="page-header">
        <h2>Settings</h2>
        <p className="page-subtitle">スキャン・解析・整理の動作設定を変更できます。</p>
      </header>

      <QueryState
        isLoading={settings.isPending}
        isError={settings.isError}
        error={settings.error}
        isEmpty={false}
        loadingMessage="設定を読み込み中..."
      />

      {!settings.isPending && !settings.isError && (
        <>
          {/* ライブラリ統計 */}
          <article className="card">
            <h3 className="section-title">ライブラリ情報</h3>
            <div className="card-grid" style={{ marginTop: 12 }}>
              <div className="stat-mini"><span className="muted">総ファイル数</span><strong>{stats.data?.total ?? '-'}</strong></div>
              <div className="stat-mini"><span className="muted">解析済み</span><strong>{stats.data?.analyzed ?? '-'}</strong></div>
              <div className="stat-mini"><span className="muted">トリアージ済み</span><strong>{stats.data?.triaged ?? '-'}</strong></div>
              <div className="stat-mini"><span className="muted">未処理</span><strong>{stats.data?.unprocessed ?? '-'}</strong></div>
              <div className="stat-mini"><span className="muted">ゴミ箱</span><strong>{stats.data?.trashed ?? '-'}</strong></div>
            </div>
          </article>

          {/* スキャン設定 */}
          <article className="card">
            <h3 className="section-title">スキャン設定</h3>
            <div className="settings-list">
              <SettingRow
                label="ルートフォルダ"
                description="スキャン対象のベースフォルダパス"
                value={rootPath}
                onChange={setRootPath}
                onSave={() => save('root_path', rootPath)}
                saving={savingKey === 'root_path'}
              />
            </div>
          </article>

          {/* 解析設定 */}
          <article className="card">
            <h3 className="section-title">解析設定</h3>
            <div className="settings-list">
              <SettingRow
                label="ブレ検出閾値"
                description="この値より低いブレスコアをぼけとして検出（デフォルト: 20）"
                value={blurThreshold}
                onChange={setBlurThreshold}
                onSave={() => save('blur_threshold', blurThreshold)}
                saving={savingKey === 'blur_threshold'}
                type="number"
                min={1}
                max={200}
              />
              <SettingRow
                label="類似度閾値"
                description="この値以内のハミング距離を類似として判定（デフォルト: 5、最大: 25）"
                value={simThreshold}
                onChange={setSimThreshold}
                onSave={() => save('similarity_threshold', simThreshold)}
                saving={savingKey === 'similarity_threshold'}
                type="number"
                min={1}
                max={25}
              />
            </div>
          </article>

          {/* ゴミ箱設定 */}
          <article className="card">
            <h3 className="section-title">ゴミ箱設定</h3>
            <div className="settings-list">
              <SettingRow
                label="ゴミ箱保持期間（日）"
                description="ゴミ箱に入れてからこの日数が経過するまで完全削除できません（デフォルト: 14）"
                value={retentionDays}
                onChange={setRetentionDays}
                onSave={() => save('trash_retention_days', retentionDays)}
                saving={savingKey === 'trash_retention_days'}
                type="number"
                min={0}
                max={365}
              />
            </div>
          </article>
          {/* DB 管理 */}
          <article className="card" style={{ borderColor: '#6e2d38' }}>
            <h3 className="section-title" style={{ color: 'var(--danger)' }}>DB 管理（危険な操作）</h3>
            <div className="settings-list">
              <div className="setting-row">
                <div className="setting-info">
                  <p className="setting-label">解析結果をリセット</p>
                  <p className="muted setting-desc">
                    blur_score・サムネイル・ハッシュを全消去し、全ファイルを未解析状態に戻します。<br />
                    ブレ検知ロジック変更後に再解析し直す場合に使用します。ファイル自体は削除されません。
                  </p>
                </div>
                <div>
                  {confirmAction === 'reset-analysis' ? (
                    <div className="row">
                      <span className="muted" style={{ fontSize: 12 }}>本当にリセットしますか？</span>
                      <button className="button danger" onClick={() => resetAnalysisMutation.mutate()}
                        disabled={resetAnalysisMutation.isPending}>
                        {resetAnalysisMutation.isPending ? <Spinner size={14} inline /> : '実行'}
                      </button>
                      <button className="button ghost" onClick={() => setConfirmAction(null)}>キャンセル</button>
                    </div>
                  ) : (
                    <button className="button danger" onClick={() => setConfirmAction('reset-analysis')}>
                      解析リセット
                    </button>
                  )}
                </div>
              </div>
              <div className="setting-row">
                <div className="setting-info">
                  <p className="setting-label">DB を全消去</p>
                  <p className="muted setting-desc">
                    登録済みの全ファイル情報・サムネイルを DB から削除します。<br />
                    スキャンからやり直す場合に使用します。元の画像ファイルは削除されません。
                  </p>
                </div>
                <div>
                  {confirmAction === 'clear-all' ? (
                    <div className="row">
                      <span className="muted" style={{ fontSize: 12 }}>本当に全消去しますか？</span>
                      <button className="button danger" onClick={() => clearAllMutation.mutate()}
                        disabled={clearAllMutation.isPending}>
                        {clearAllMutation.isPending ? <Spinner size={14} inline /> : '実行'}
                      </button>
                      <button className="button ghost" onClick={() => setConfirmAction(null)}>キャンセル</button>
                    </div>
                  ) : (
                    <button className="button danger" onClick={() => setConfirmAction('clear-all')}>
                      全消去
                    </button>
                  )}
                </div>
              </div>
            </div>
          </article>
        </>
      )}
    </section>
  )
}

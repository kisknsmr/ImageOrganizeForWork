import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink } from 'react-router-dom'
import { api } from '../api/client'
import { BrandIcon } from './icons'
import { NAV_ICON_MAP, type NavIconName } from './navIcons'
import { getApiErrorMessage, useToast } from './useToast'

type NavItem = {
  to: string
  label: string
  icon: NavIconName
  tooltip?: string
  end?: boolean
}

type NavSection = {
  title: string
  items: NavItem[]
}

const sections: NavSection[] = [
  {
    title: 'IMPORT',
    items: [
      { to: '/preprocess', label: 'Preprocess', icon: 'import', tooltip: '取込前に画像/動画/その他フォルダへ振り分け' },
    ],
  },
  {
    title: 'LIBRARY',
    items: [
      { to: '/', label: 'Home', icon: 'home', tooltip: '進捗・メッセージの表示', end: true },
      { to: '/gallery', label: 'Gallery', icon: 'gallery', tooltip: 'ライブラリの一覧表示' },
      { to: '/triage', label: 'Triage', icon: 'manual', tooltip: 'Keep/Discard/Skip でテンポ良く判定' },
    ],
  },
  {
    title: 'CLEAN UP',
    items: [
      { to: '/duplicates', label: 'Duplicates', icon: 'duplicate', tooltip: '完全に同じ画像を検出・削除' },
      { to: '/blurry', label: 'Blurry photos', icon: 'blur', tooltip: 'ブレ・撮影ミスを検出・削除' },
      { to: '/tiny', label: 'Tiny files', icon: 'tiny', tooltip: 'サムネサイズ級の不要ファイル除去' },
      { to: '/similar', label: 'Similar groups', icon: 'similar', tooltip: '激似・連写をまとめて確認' },
      { to: '/manual', label: 'Manual sort', icon: 'manual', tooltip: '残す／捨てる・フォルダ分け' },
      { to: '/cleanup', label: 'Clean up summary', icon: 'cleanup', tooltip: 'カテゴリごとの集計' },
    ],
  },
  {
    title: 'SMART',
    items: [
      { to: '/ai-organize', label: 'Smart organize', icon: 'ai', tooltip: 'イベント単位のスマート整理' },
    ],
  },
]

function NavItemRow({ item }: { item: NavItem }) {
  const Icon = NAV_ICON_MAP[item.icon]
  return (
    <NavLink
      to={item.to}
      end={item.end ?? item.to === '/'}
      className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
      title={item.tooltip}
    >
      <span className="nav-link-icon" aria-hidden="true">
        <Icon size={15} />
      </span>
      <span className="nav-link-label">{item.label}</span>
    </NavLink>
  )
}

export function Sidebar() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 5000 })
  const TrashIcon = NAV_ICON_MAP.trash
  const SettingsIcon = NAV_ICON_MAP.settings
  const ResetIcon = NAV_ICON_MAP.reset

  const resetAnalysis = useMutation({
    mutationFn: (rootPath: string) => api.analyzeReset(rootPath),
    onSuccess: (res) => {
      toast.success(`${res.reset}件を未解析に戻しました`, 'Reset')
      queryClient.invalidateQueries()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '解析結果のリセットに失敗しました')
    },
  })

  const handleResetAnalysis = () => {
    const rootPath = stats.data?.root_path
    if (!rootPath) return
    const analyzed = stats.data?.analyzed ?? 0
    const confirmed = window.confirm(
      `現在のライブラリ「${rootPath}」の解析結果をリセットします。\n` +
        `解析済み ${analyzed}件が未解析に戻り、再度 Start Analyze が必要になります。\n` +
        '（Keep/Discard等の判定やゴミ箱の状態は変わりません）\n実行しますか？',
    )
    if (confirmed) resetAnalysis.mutate(rootPath)
  }

  return (
    <aside className="sidebar">
      <header className="sidebar-brand">
        <BrandIcon size={28} />
        <div className="sidebar-brand-text">
          <span className="sidebar-brand-name">PhotoSortX</span>
          <span className="sidebar-brand-version">Tauri v3.0</span>
        </div>
      </header>

      <nav className="sidebar-nav" aria-label="主要メニュー">
        {sections.map((section) => (
          <div key={section.title} className="nav-section">
            <p className="nav-title">{section.title}</p>
            {section.items.map((item) => (
              <NavItemRow key={item.to} item={item} />
            ))}
          </div>
        ))}
      </nav>

      <footer className="sidebar-footer">
        <div className="sidebar-footer-info">
          <span className="lib-stat" title="ライブラリ件数">
            {stats.data?.total != null ? `${stats.data.total.toLocaleString()} files` : '—'}
          </span>
          {typeof stats.data?.trashed === 'number' && stats.data.trashed > 0 && (
            <span className="lib-stat muted">({stats.data.trashed.toLocaleString()} trashed)</span>
          )}
        </div>
        <button
          type="button"
          className="sidebar-icon-button"
          title="現在のライブラリの解析結果をリセット（未解析に戻す）"
          aria-label="Reset analysis"
          disabled={!stats.data?.root_path || resetAnalysis.isPending}
          onClick={handleResetAnalysis}
        >
          <ResetIcon size={15} />
        </button>
        <NavLink
          to="/trash"
          className={({ isActive }) => `sidebar-icon-button ${isActive ? 'active' : ''}`}
          title="削除済みファイルの一覧"
          aria-label="Trash"
        >
          <TrashIcon size={15} />
        </NavLink>
        <NavLink
          to="/settings"
          className={({ isActive }) => `sidebar-icon-button ${isActive ? 'active' : ''}`}
          title="設定"
          aria-label="Settings"
        >
          <SettingsIcon size={15} />
        </NavLink>
      </footer>
    </aside>
  )
}

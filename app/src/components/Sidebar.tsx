import { useQuery } from '@tanstack/react-query'
import { NavLink } from 'react-router-dom'
import { api } from '../api/client'
import { BrandIcon } from './icons'
import { NAV_ICON_MAP, type NavIconName } from './navIcons'

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
    title: 'OVERVIEW',
    items: [
      { to: '/', label: 'Dashboard', icon: 'home', tooltip: '概要・取込・解析・整理サマリー', end: true },
    ],
  },
  {
    title: 'LIBRARY',
    items: [
      { to: '/gallery', label: 'Gallery', icon: 'gallery', tooltip: 'ライブラリの一覧表示' },
      { to: '/triage', label: 'Triage', icon: 'manual', tooltip: 'Keep/Discard/Skip でテンポ良く判定' },
    ],
  },
  {
    title: 'CLEAN UP — 削除',
    items: [
      { to: '/duplicates', label: 'Duplicates', icon: 'duplicate', tooltip: '完全に同じ画像を検出・削除' },
      { to: '/blurry', label: 'Blurry photos', icon: 'blur', tooltip: 'ブレ・撮影ミスを検出・削除' },
      { to: '/tiny', label: 'Tiny files', icon: 'tiny', tooltip: 'サムネサイズ級の不要ファイル除去' },
      { to: '/similar', label: 'Similar groups', icon: 'similar', tooltip: '激似・連写をまとめて確認' },
    ],
  },
  {
    title: 'CLEAN UP — 移動',
    items: [
      { to: '/manual', label: 'Manual sort', icon: 'manual', tooltip: '残す／捨てる・フォルダ分け' },
      { to: '/separate', label: 'Separate', icon: 'import', tooltip: '画像と動画をフォルダ構造を保ったまま分離' },
      { to: '/smart-sort', label: 'Smart Sort', icon: 'cleanup', tooltip: 'ローカルAI（CLIP）によるフォルダ仕分け' },
    ],
  },
  {
    title: 'SMART',
    items: [
      { to: '/ai-organize', label: 'AI Organize', icon: 'ai', tooltip: '生成AI APIを使った高度な整理（準備中）' },
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
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 5000 })
  const TrashIcon = NAV_ICON_MAP.trash
  const SettingsIcon = NAV_ICON_MAP.settings

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

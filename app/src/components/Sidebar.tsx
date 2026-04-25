import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Home' },
  { to: '/gallery', label: 'Gallery' },
  { to: '/import', label: 'Import' },
  { to: '/triage', label: 'Triage' },
  { to: '/cleanup', label: 'Clean up' },
]

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>PhotoSortX</h1>
        <p>Tauri Edition</p>
      </div>
      <nav className="nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}


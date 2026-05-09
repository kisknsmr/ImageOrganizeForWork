export function SettingsPage() {
  return (
    <section className="page">
      <header className="page-header">
        <h2>Settings</h2>
        <p className="page-subtitle">既存設定との互換性を保ちつつ、Tauri側設定UIを段階的に拡張します。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Legacy compatible
          </span>
        </div>
      </div>
      <article className="card">
        <p className="muted">
          安全のため、既存のPyQt設定画面は削除せず維持しています。Tauri側設定は段階的に移行します。
        </p>
      </article>
    </section>
  )
}


export function TinyFilesPage() {
  return (
    <section className="page">
      <header className="page-header">
        <h2>Tiny Files</h2>
        <p className="page-subtitle">低サイズファイルの整理機能を、既存機能互換を保ちながら段階移行しています。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Migration in progress
          </span>
        </div>
      </div>
      <article className="card">
        <p className="muted">
          既存PyQtの「小さいファイル削除」と同等機能は順次移行中です。現時点では入口ページとして維持しています。
        </p>
      </article>
    </section>
  )
}


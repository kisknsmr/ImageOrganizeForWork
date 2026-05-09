export function AiOrganizePage() {
  return (
    <section className="page">
      <header className="page-header">
        <h2>AI Organize</h2>
        <p className="page-subtitle">既存のPythonコアを再利用し、AI整理の操作体験を段階的に移植しています。</p>
      </header>
      <div className="toolbar">
        <div className="toolbar-group">
          <span className="status-chip">
            <span className="status-dot" />
            Core integration planned
          </span>
        </div>
      </div>
      <article className="card">
        <p className="muted">
          CLIPベースの既存スマート整理機能は、Pythonコアを再利用して段階的にTauriへ移行します。
          現時点ではUI骨格を維持し、既存PyQt版はそのまま使用可能です。
        </p>
      </article>
    </section>
  )
}


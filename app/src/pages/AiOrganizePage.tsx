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
          イベント単位の整理や CLIP 連携は今後の拡張として計画しています。現時点では UI の骨組みのみです。
        </p>
      </article>
    </section>
  )
}


import './App.css'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { CleanupPage } from './pages/CleanupPage'
import { GalleryPage } from './pages/GalleryPage'
import { HomePage } from './pages/HomePage'
import { ImportPage } from './pages/ImportPage'
import { TriagePage } from './pages/TriagePage'

function App() {
  return (
    <HashRouter>
      <div className="app-shell">
        <Sidebar />
        <main className="content">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/gallery" element={<GalleryPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/triage" element={<TriagePage />} />
            <Route path="/cleanup" element={<CleanupPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  )
}

export default App

import './App.css'
import { useEffect, useRef } from 'react'
import { HashRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { BackendGate } from './components/BackendGate'
import { Sidebar } from './components/Sidebar'
import { ToastProvider } from './components/Toast'
import { AiOrganizePage } from './pages/AiOrganizePage'
import { BlurryPage } from './pages/BlurryPage'
import { CleanupPage } from './pages/CleanupPage'
import { DuplicatesPage } from './pages/DuplicatesPage'
import { GalleryPage } from './pages/GalleryPage'
import { HomePage } from './pages/HomePage'
import { ManualSortPage } from './pages/ManualSortPage'
import { PreprocessPage } from './pages/PreprocessPage'
import { SettingsPage } from './pages/SettingsPage'
import { SimilarPage } from './pages/SimilarPage'
import { TinyFilesPage } from './pages/TinyFilesPage'
import { TrashPage } from './pages/TrashPage'
import { TriagePage } from './pages/TriagePage'

function AnimatedRoutes() {
  const location = useLocation()
  return (
    <div className="page-transition" key={location.pathname}>
      <Routes location={location}>
        <Route path="/" element={<HomePage />} />
        <Route path="/preprocess" element={<PreprocessPage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/triage" element={<TriagePage />} />
        <Route path="/duplicates" element={<DuplicatesPage />} />
        <Route path="/blurry" element={<BlurryPage />} />
        <Route path="/tiny" element={<TinyFilesPage />} />
        <Route path="/similar" element={<SimilarPage />} />
        <Route path="/manual" element={<ManualSortPage />} />
        <Route path="/ai-organize" element={<AiOrganizePage />} />
        <Route path="/cleanup" element={<CleanupPage />} />
        <Route path="/trash" element={<TrashPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

/**
 * 本文だけがスクロール領域なので、ページ遷移時にその位置を先頭へ戻す。
 * （戻さないと新しいページが途中から表示され、ヘッダーが見えない）
 */
function ContentRegion() {
  const location = useLocation()
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    ref.current?.scrollTo({ top: 0 })
  }, [location.pathname])

  return (
    <main className="content" id="main-content" ref={ref}>
      <AnimatedRoutes />
    </main>
  )
}

function App() {
  return (
    <HashRouter>
      <ToastProvider>
        <BackendGate>
          <div className="app-shell">
            <Sidebar />
            <ContentRegion />
          </div>
        </BackendGate>
      </ToastProvider>
    </HashRouter>
  )
}

export default App

import './App.css'
import { HashRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { ToastProvider } from './components/Toast'
import { AiOrganizePage } from './pages/AiOrganizePage'
import { SeparatePage } from './pages/SeparatePage'
import { EmptyFoldersPage } from './pages/EmptyFoldersPage'
import { SmartSortPage } from './pages/SmartSortPage'
import { BlurryPage } from './pages/BlurryPage'
import { CleanupPage } from './pages/CleanupPage'
import { DuplicatesPage } from './pages/DuplicatesPage'
import { GalleryPage } from './pages/GalleryPage'
import { HomePage } from './pages/HomePage'
import { ImportPage } from './pages/ImportPage'
import { ManualSortPage } from './pages/ManualSortPage'
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
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/import" element={<Navigate to="/" replace />} />
        <Route path="/cleanup" element={<Navigate to="/" replace />} />
        <Route path="/triage" element={<TriagePage />} />
        <Route path="/duplicates" element={<DuplicatesPage />} />
        <Route path="/blurry" element={<BlurryPage />} />
        <Route path="/tiny" element={<TinyFilesPage />} />
        <Route path="/similar" element={<SimilarPage />} />
        <Route path="/manual" element={<ManualSortPage />} />
        <Route path="/ai-organize" element={<AiOrganizePage />} />
        <Route path="/smart-sort" element={<SmartSortPage />} />
        <Route path="/separate" element={<SeparatePage />} />
        <Route path="/empty-folders" element={<EmptyFoldersPage />} />
        <Route path="/trash" element={<TrashPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

function App() {
  return (
    <HashRouter>
      <ToastProvider>
        <div className="app-shell">
          <Sidebar />
          <main className="content">
            <AnimatedRoutes />
          </main>
        </div>
      </ToastProvider>
    </HashRouter>
  )
}

export default App

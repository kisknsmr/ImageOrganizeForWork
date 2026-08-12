import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

/*
 * バックエンドはアプリと同時に起動するため、最初の数回は接続に失敗しうる。
 * 既定でリトライさせ、短時間の重複フェッチは staleTime で抑える。
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 4000),
      staleTime: 5000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)

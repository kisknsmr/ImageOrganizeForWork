import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api } from '../api/client'
import { useToast } from './useToast'

const KIND_LABELS: Record<string, string> = {
  scan: 'スキャン',
  analyze: '解析',
  preprocess: '振り分け',
  full_hash: '完全ハッシュ計算',
}

/**
 * バックグラウンドジョブ(scan/analyze/preprocess)の状態をポーリングし、
 * running: true → false の遷移を検知して完了トーストを出す。
 * ジョブが数秒未満で終わるケース（例: 少数ファイルの振り分け）でも
 * 開始直後に一度即座に再取得することで、進捗ポーリング(2000ms間隔)の
 * 取りこぼしを減らす。
 */
export function useJobStatus() {
  const toast = useToast()
  const status = useQuery({
    queryKey: ['scanStatus'],
    queryFn: api.scanStatus,
    refetchInterval: (query) => (query.state.data?.running ? 400 : 2000),
  })

  const wasRunning = useRef(false)

  useEffect(() => {
    const running = status.data?.running ?? false
    if (wasRunning.current && !running) {
      const label = status.data?.kind ? (KIND_LABELS[status.data.kind] ?? status.data.kind) : 'ジョブ'
      if (status.data?.error) {
        toast.error(status.data.error, `${label}でエラー`)
      } else {
        toast.success(status.data?.message ?? '完了しました', `${label}完了`)
      }
    }
    wasRunning.current = running
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.data?.running, status.data?.message, status.data?.error, status.data?.kind])

  const jobRunning = status.data?.running ?? false
  const jobKindLabel =
    status.data?.kind === 'analyze' ? '解析中' : status.data?.kind === 'preprocess' ? '仕分け中' : 'スキャン中'

  return { status, jobRunning, jobKindLabel, refetchStatus: status.refetch }
}

import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import { BrandIcon } from './icons'

/** これを過ぎても応答がなければ、起動待ちではなく異常として案内を出す（秒） */
const GRACE_SECONDS = 20

/**
 * バックエンド(uvicorn)が応答するまでアプリ本体をマウントしない。
 *
 * uvicorn の起動には 1〜2 秒かかるため、素通しすると各ページが一斉に
 * 「APIサーバーに接続できません」を表示してしまう。起動待ちと本当の異常は
 * 区別して見せる。
 */
export function BackendGate({ children }: { children: ReactNode }) {
  const [elapsed, setElapsed] = useState(0)

  const health = useQuery({
    queryKey: ['backend-health'],
    queryFn: api.health,
    // 起動待ちの間は短い間隔で叩きたいので、既定のリトライ/バックオフは使わない
    retry: false,
    refetchInterval: (query) => (query.state.data?.ok ? false : 800),
    gcTime: 0,
  })

  const ready = health.data?.ok === true

  useEffect(() => {
    if (ready) return
    const timer = setInterval(() => setElapsed((sec) => sec + 1), 1000)
    return () => clearInterval(timer)
  }, [ready])

  if (ready) return <>{children}</>

  const stalled = elapsed >= GRACE_SECONDS

  return (
    <div className="startup">
      <div className="startup-card">
        <BrandIcon size={48} />
        <h1 className="startup-title">PhotoSortX</h1>

        {stalled ? (
          <>
            <p className="startup-message">バックエンドが応答しません。</p>
            <div className="startup-help">
              <p>次のいずれかを確認してください。</p>
              <ol>
                <li>
                  リポジトリ直下に <code>.venv</code> があること
                  （無ければ <code className="mono">python -m venv .venv</code> の後に
                  <code className="mono">.venv\Scripts\pip install -r requirements.txt</code>）
                </li>
                <li>
                  ポート 8765 が他のプロセスに使われていないこと
                </li>
                <li>
                  手動起動で切り分ける:{' '}
                  <code className="mono">.venv\Scripts\python -m uvicorn src.api_server:app --port 8765</code>
                </li>
              </ol>
            </div>
            <button className="button" type="button" onClick={() => health.refetch()}>
              再試行
            </button>
          </>
        ) : (
          <>
            <p className="startup-message">バックエンドを起動しています...</p>
            <progress className="startup-progress" />
            <p className="startup-hint">{elapsed} 秒経過</p>
          </>
        )}
      </div>
    </div>
  )
}

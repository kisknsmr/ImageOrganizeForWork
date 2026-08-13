import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import { Spinner } from './Spinner'
import { getApiErrorMessage, useToast } from './useToast'

type JobControlsProps = {
  paused: boolean
  onChanged: () => void
}

/**
 * 実行中ジョブの一時停止／再開／中止。
 *
 * 一時停止はバッチ境界で効くため、押してから実際に止まるまで少し間がある。
 * 中止しても処理済みの分は DB に残るので、後から続きを再開できる。
 */
export function JobControls({ paused, onChanged }: JobControlsProps) {
  const toast = useToast()

  const pause = useMutation({
    mutationFn: api.jobsPause,
    onSuccess: onChanged,
    onError: (e) => toast.error(getApiErrorMessage(e), '一時停止できませんでした'),
  })
  const resume = useMutation({
    mutationFn: api.jobsResume,
    onSuccess: onChanged,
    onError: (e) => toast.error(getApiErrorMessage(e), '再開できませんでした'),
  })
  const cancel = useMutation({
    mutationFn: api.jobsCancel,
    onSuccess: onChanged,
    onError: (e) => toast.error(getApiErrorMessage(e), '中止できませんでした'),
  })

  const busy = pause.isPending || resume.isPending || cancel.isPending

  return (
    <div className="toolbar-group">
      {paused ? (
        <button
          className="button"
          type="button"
          disabled={busy}
          onClick={() => resume.mutate()}
          title="処理を再開する"
        >
          {resume.isPending ? <Spinner size={14} inline /> : null}
          再開
        </button>
      ) : (
        <button
          className="button secondary"
          type="button"
          disabled={busy}
          onClick={() => pause.mutate()}
          title="処理を一時停止する（進捗は保持されます）"
        >
          {pause.isPending ? <Spinner size={14} inline /> : null}
          一時停止
        </button>
      )}
      <button
        className="button ghost"
        type="button"
        disabled={busy}
        onClick={() => {
          if (window.confirm('処理を中止しますか？\nここまで処理した分は保存され、後から続きを実行できます。')) {
            cancel.mutate()
          }
        }}
        title="処理を中止する（処理済みの分は保存されます）"
      >
        中止
      </button>
    </div>
  )
}

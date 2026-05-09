type QueryStateProps = {
  isLoading: boolean
  isError: boolean
  error: unknown
  isEmpty: boolean
  loadingMessage?: string
  emptyMessage?: string
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'unknown error'
}

export function QueryState({
  isLoading,
  isError,
  error,
  isEmpty,
  loadingMessage = '読み込み中です...',
  emptyMessage = '表示するデータがありません。',
}: QueryStateProps) {
  if (isLoading) {
    return (
      <article className="card state-card">
        <p className="state-text">{loadingMessage}</p>
      </article>
    )
  }
  if (isError) {
    return (
      <article className="card state-card state-error">
        <p className="state-text">データ取得に失敗しました: {getErrorMessage(error)}</p>
      </article>
    )
  }
  if (isEmpty) {
    return (
      <article className="card state-card">
        <p className="state-text">{emptyMessage}</p>
      </article>
    )
  }
  return null
}

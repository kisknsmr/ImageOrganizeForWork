import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { LibraryClearScope } from '../types'
import { getApiErrorMessage, useToast } from './useToast'

/**
 * 前回の読み込み記録を消す操作。Home と Settings の両方から呼ぶ。
 *
 * 破壊的に見える操作なので、実行前に「何が消えて何が消えないか」を確認させる。
 */
export function useClearLibrary() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (scope: LibraryClearScope) => api.libraryClear(scope),
    onSuccess: (res) => {
      const kept = res.kept_trash > 0 ? `（ゴミ箱の ${res.kept_trash} 件は残しました）` : ''
      toast.success(`読み込み記録 ${res.deleted.toLocaleString()} 件を消去しました${kept}`, 'Library')
      // 件数・一覧・フォルダ候補がすべて変わるので全体を無効化する
      queryClient.invalidateQueries()
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error), '読み込み記録の消去に失敗しました')
    },
  })

  const clear = (scope: LibraryClearScope, context: { total?: number; rootPath?: string | null }) => {
    const target =
      scope === 'all'
        ? 'これまでに読み込んだ**すべての**記録'
        : `「${context.rootPath ?? '現在のライブラリ'}」の読み込み記録`
    const count = context.total != null ? `${context.total.toLocaleString()} 件の` : ''

    const confirmed = window.confirm(
      `${target}を消去します。\n\n` +
        `・${count}ファイル記録とサムネイルが DB から消えます\n` +
        '・ディスク上の画像ファイルは削除されません（再スキャンで戻せます）\n' +
        '・ゴミ箱に入れたファイルの記録は残します（消すと復元できなくなるため）\n\n' +
        '実行しますか？',
    )
    if (confirmed) mutation.mutate(scope)
  }

  return { clear, isPending: mutation.isPending }
}

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'

// Tauri 環境かどうかを判定
const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function pickFolderDialog(): Promise<string | null> {
  if (!isTauri) return null
  const { open } = await import('@tauri-apps/plugin-dialog')
  const selected = await open({ directory: true, multiple: false })
  if (typeof selected === 'string') return selected
  return null
}

type FolderPickerProps = {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  label?: string
}

/**
 * フォルダパス入力 + OSフォルダ選択ダイアログ + 選択直後のファイル数プレビュー。
 * ImportPanel / PreprocessPage で共通利用する。
 */
export function FolderPicker({ value, onChange, disabled, label = 'Selected Folder' }: FolderPickerProps) {
  const [checkedPath, setCheckedPath] = useState('')

  // フォルダ選択直後・入力確定時にファイル数を先に表示する（実際のスキャン/登録はまだ行わない）
  const folderCheck = useQuery({
    queryKey: ['scanCheck', checkedPath],
    queryFn: () => api.scanCheck(checkedPath),
    enabled: checkedPath.trim().length > 0,
  })

  const handlePickFolder = async () => {
    const path = await pickFolderDialog()
    if (path) {
      onChange(path)
      setCheckedPath(path)
    }
  }

  const confirmPath = () => {
    if (value.trim()) setCheckedPath(value.trim())
  }

  return (
    <>
      <label className="label" htmlFor="root-path">
        {label}
      </label>
      <div className="row">
        <input
          id="root-path"
          className="input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={confirmPath}
          onKeyDown={(e) => {
            if (e.key === 'Enter') confirmPath()
          }}
          placeholder="D:/Pictures"
          disabled={disabled}
        />
        {isTauri && (
          <button
            className="button ghost"
            type="button"
            onClick={handlePickFolder}
            disabled={disabled}
            title="フォルダを選択"
          >
            参照...
          </button>
        )}
      </div>
      {checkedPath && (
        <p className="muted">
          {folderCheck.isFetching
            ? 'ファイル数を確認中...'
            : folderCheck.data
              ? folderCheck.data.valid
                ? `${folderCheck.data.disk_count}件のファイルが見つかりました${
                    folderCheck.data.total > 0
                      ? `（登録済み${folderCheck.data.total}件 / 未解析${folderCheck.data.unprocessed}件）`
                      : ''
                  }`
                : 'フォルダが見つかりません'
              : ''}
        </p>
      )}
    </>
  )
}

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { PreprocessMode } from '../types'

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
  /**
   * 件数を数える基準。実行する処理と揃える必要がある。
   *   scan       … 取込対象（対応拡張子のみ／カテゴリフォルダの中も含む）
   *   preprocess … 振り分け対象（全拡張子／カテゴリフォルダの外だけ）
   * ずれると「見つかった件数」と処理結果の件数が食い違って見える。
   */
  countMode?: 'scan' | 'preprocess'
  /** countMode='preprocess' のときの走査モード。件数は実行時と同じ基準で数える */
  preprocessMode?: PreprocessMode
}

/**
 * フォルダパス入力 + OSフォルダ選択ダイアログ + 選択直後のファイル数プレビュー。
 * ImportPanel / PreprocessPage で共通利用する。
 */
export function FolderPicker({
  value,
  onChange,
  disabled,
  label = 'Selected Folder',
  countMode = 'scan',
  preprocessMode = 'incremental',
}: FolderPickerProps) {
  const [checkedPath, setCheckedPath] = useState('')
  const enabled = checkedPath.trim().length > 0

  // フォルダ選択直後・入力確定時にファイル数を先に表示する（実際の処理はまだ行わない）
  const scanCheck = useQuery({
    queryKey: ['scanCheck', checkedPath],
    queryFn: () => api.scanCheck(checkedPath),
    enabled: enabled && countMode === 'scan',
  })
  const preprocessCheck = useQuery({
    queryKey: ['preprocessCheck', checkedPath, preprocessMode],
    queryFn: () => api.preprocessCheck(checkedPath, preprocessMode),
    enabled: enabled && countMode === 'preprocess',
  })
  const check = countMode === 'preprocess' ? preprocessCheck : scanCheck

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
          {check.isFetching ? 'ファイル数を確認中...' : null}
          {!check.isFetching && check.data && !check.data.valid ? 'フォルダが見つかりません' : null}
          {!check.isFetching && preprocessCheck.data?.valid && countMode === 'preprocess'
            ? `走査 ${preprocessCheck.data.all_files.toLocaleString()} 件` +
              ` ／ 振り分け対象 ${preprocessCheck.data.total.toLocaleString()} 件` +
              `（未振り分け ${preprocessCheck.data.unsorted.toLocaleString()}` +
              (preprocessCheck.data.misplaced > 0
                ? ` ・要見直し ${preprocessCheck.data.misplaced.toLocaleString()}`
                : '') +
              `／画像 ${preprocessCheck.data.pictures.toLocaleString()} ・ ` +
              `動画 ${preprocessCheck.data.movies.toLocaleString()} ・ ` +
              `その他 ${preprocessCheck.data.others.toLocaleString()}）` +
              ` ／ 対応不要 ${preprocessCheck.data.already_sorted.toLocaleString()} 件`
            : null}
          {!check.isFetching && scanCheck.data?.valid && countMode === 'scan'
            ? `${scanCheck.data.disk_count.toLocaleString()}件のファイルが見つかりました` +
              (scanCheck.data.total > 0
                ? `（登録済み${scanCheck.data.total.toLocaleString()}件 / 未解析${scanCheck.data.unprocessed.toLocaleString()}件）`
                : '')
            : null}
        </p>
      )}
    </>
  )
}

/** バイト数を人が読める単位にする */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/** Unix 秒をローカル表記の日時にする */
export function formatTimestamp(seconds: number): string {
  if (!seconds) return '-'
  return new Date(seconds * 1000).toLocaleString()
}

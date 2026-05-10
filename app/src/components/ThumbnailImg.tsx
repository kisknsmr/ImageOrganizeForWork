// サムネが存在しない（404）場合はプレースホルダーを表示する img ラッパー
const PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120' viewBox='0 0 120 120'%3E%3Crect width='120' height='120' fill='%231a2540'/%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' font-size='32' fill='%23334466'%3E%F0%9F%96%BC%3C/text%3E%3C/svg%3E"

type Props = React.ImgHTMLAttributes<HTMLImageElement>

export function ThumbnailImg({ onError, ...props }: Props) {
  const handleError = (e: React.SyntheticEvent<HTMLImageElement>) => {
    e.currentTarget.src = PLACEHOLDER
    onError?.(e)
  }
  return <img {...props} onError={handleError} />
}

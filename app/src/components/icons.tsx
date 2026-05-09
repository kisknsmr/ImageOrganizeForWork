import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & {
  size?: number
}

const STROKE = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.4,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const

function Svg({ size = 16, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  )
}

export function HomeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M 8 1.28 L 14.72 8.32 L 1.28 8.32 Z" {...STROKE} />
      <rect x="2.88" y="8.32" width="10.24" height="6.4" {...STROKE} />
      <rect x="6.08" y="10.56" width="3.84" height="4.16" {...STROKE} />
    </Svg>
  )
}

export function GalleryIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="0.96" y="0.96" width="6.24" height="6.24" {...STROKE} />
      <rect x="8.8" y="0.96" width="6.24" height="6.24" {...STROKE} />
      <rect x="0.96" y="8.8" width="6.24" height="6.24" {...STROKE} />
      <rect x="8.8" y="8.8" width="6.24" height="6.24" {...STROKE} />
    </Svg>
  )
}

export function ImportIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <line x1="8" y1="1.92" x2="8" y2="12.16" {...STROKE} />
      <line x1="8" y1="1.92" x2="4" y2="5.92" {...STROKE} />
      <line x1="8" y1="1.92" x2="12" y2="5.92" {...STROKE} />
      <line x1="2.4" y1="14.08" x2="13.6" y2="14.08" {...STROKE} />
    </Svg>
  )
}

export function DuplicateIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4.48" y="0.96" width="9.92" height="9.92" {...STROKE} />
      <rect x="1.28" y="4.48" width="9.92" height="9.92" {...STROKE} />
    </Svg>
  )
}

export function BlurIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="2.56" {...STROKE} />
      <circle cx="8" cy="8" r="5.44" {...STROKE} />
      <circle cx="8" cy="8" r="7.5" {...STROKE} strokeDasharray="2 2" />
    </Svg>
  )
}

export function TinyFileIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M 2.24 0.64 L 10.24 0.64 L 13.76 4.16 L 13.76 15.36 L 2.24 15.36 Z"
        {...STROKE}
      />
      <polyline points="10.24,0.64 10.24,4.16 13.76,4.16" {...STROKE} />
      <line x1="4.16" y1="7.68" x2="11.52" y2="7.68" {...STROKE} />
      <line x1="4.16" y1="9.6" x2="11.52" y2="9.6" {...STROKE} />
      <line x1="4.16" y1="11.52" x2="8.96" y2="11.52" {...STROKE} />
    </Svg>
  )
}

export function SimilarIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="0.96" y="0.96" width="4.8" height="4.8" {...STROKE} />
      <rect x="7.04" y="0.96" width="4.8" height="4.8" {...STROKE} />
      <rect x="0.96" y="7.04" width="4.8" height="4.8" {...STROKE} />
      <rect x="7.04" y="7.04" width="4.8" height="4.8" {...STROKE} />
    </Svg>
  )
}

export function ManualSortIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="1.28" y="1.28" width="13.44" height="13.44" {...STROKE} />
      <polyline points="3.84,8.32 7.04,11.52 12.16,4.8" {...STROKE} />
    </Svg>
  )
}

export function AiIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M 8 0.96 L 9.76 6.24 L 15.04 8 L 9.76 9.76 L 8 15.04 L 6.24 9.76 L 0.96 8 L 6.24 6.24 Z"
        fill="currentColor"
      />
    </Svg>
  )
}

export function TrashIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <line x1="1.6" y1="4.16" x2="14.4" y2="4.16" {...STROKE} />
      <rect x="2.88" y="4.8" width="10.24" height="9.92" {...STROKE} />
      <line x1="6.08" y1="1.6" x2="9.92" y2="1.6" {...STROKE} />
      <line x1="6.08" y1="1.6" x2="5.12" y2="4.16" {...STROKE} />
      <line x1="9.92" y1="1.6" x2="10.88" y2="4.16" {...STROKE} />
      <line x1="6.4" y1="6.72" x2="6.4" y2="13.44" {...STROKE} />
      <line x1="9.6" y1="6.72" x2="9.6" y2="13.44" {...STROKE} />
    </Svg>
  )
}

export function SettingsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="3.2" {...STROKE} />
      {Array.from({ length: 8 }).map((_, i) => {
        const angle = (i * 45 * Math.PI) / 180
        const r1 = 6.08
        const r2 = 7.68
        const x1 = 8 + r1 * Math.cos(angle)
        const y1 = 8 + r1 * Math.sin(angle)
        const x2 = 8 + r2 * Math.cos(angle)
        const y2 = 8 + r2 * Math.sin(angle)
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} {...STROKE} />
      })}
    </Svg>
  )
}

export function CleanupIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M 4.16 7.04 L 4.16 14.4 L 11.84 14.4 L 11.84 7.04" {...STROKE} />
      <line x1="2.56" y1="7.04" x2="13.44" y2="7.04" {...STROKE} />
      <path d="M 6.4 7.04 L 6.4 4.48 C 6.4 2.88 7.04 1.6 8 1.6 C 8.96 1.6 9.6 2.88 9.6 4.48 L 9.6 7.04" {...STROKE} />
    </Svg>
  )
}

export function BrandIcon({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true">
      <rect x="0" y="0" width="28" height="28" rx="7" ry="7" fill="#3d5fc2" />
      <rect
        x="5"
        y="5"
        width="18"
        height="18"
        fill="none"
        stroke="white"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path
        d="M 6 22 L 10.6 9 L 15.1 14 L 19 9.5 L 22 22"
        fill="none"
        stroke="white"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="19" cy="9.5" r="1.6" fill="white" />
    </svg>
  )
}


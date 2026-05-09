import {
  AiIcon,
  BlurIcon,
  CleanupIcon,
  DuplicateIcon,
  GalleryIcon,
  HomeIcon,
  ImportIcon,
  ManualSortIcon,
  SettingsIcon,
  SimilarIcon,
  TinyFileIcon,
  TrashIcon,
} from './icons'

export const NAV_ICON_MAP = {
  home: HomeIcon,
  gallery: GalleryIcon,
  import: ImportIcon,
  duplicate: DuplicateIcon,
  blur: BlurIcon,
  tiny: TinyFileIcon,
  similar: SimilarIcon,
  manual: ManualSortIcon,
  ai: AiIcon,
  cleanup: CleanupIcon,
  trash: TrashIcon,
  settings: SettingsIcon,
} as const

export type NavIconName = keyof typeof NAV_ICON_MAP

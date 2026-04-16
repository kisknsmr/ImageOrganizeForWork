"""
設定管理モジュール
アプリケーション全体で使用する設定値を一元管理
"""
from dataclasses import dataclass, field
from typing import Set, Tuple, Optional
import os


@dataclass
class AppConfig:
    """アプリケーション設定クラス"""

    # ファイルサイズ制限（バイト）
    MAX_IMAGE_SIZE_FOR_ANALYSIS: int = 50 * 1024 * 1024  # 50MB
    MAX_FILE_SIZE_FOR_PROCESSING: int = 100 * 1024 * 1024  # 100MB
    MD5_READ_SIZE: int = 8192  # MD5計算時の読み込みサイズ

    # バッチ処理サイズ
    BATCH_SIZE_ANALYZER: int = 20
    BATCH_SIZE_CLUSTERING: int = 32
    BATCH_SIZE_DELETE: int = 900

    # サムネイル設定
    DEFAULT_THUMBNAIL_SIZE: int = 120
    THUMBNAIL_QUALITY: int = 70

    # 画像処理設定
    PHASH_SIZE: Tuple[int, int] = (9, 8)

    # サポート画像拡張子
    IMAGE_EXTENSIONS: Set[str] = frozenset({
        '.jpg', '.jpeg', '.png', '.heic', '.webp'
    })

    # サポート動画拡張子
    VIDEO_EXTENSIONS: Set[str] = frozenset({
        '.mp4', '.mov'
    })

    # 全サポート拡張子
    @property
    def ALL_EXTENSIONS(self) -> Set[str]:
        return self.IMAGE_EXTENSIONS | self.VIDEO_EXTENSIONS

    # データベース設定
    DB_NAME: str = "photos.db"
    DB_WAL_MODE: bool = True

    # ゴミ箱設定
    TRASH_FOLDER_NAME: str = "_TrashBox"
    # ゴミ箱に移してから「完全削除」できるまでの最短日数（退避期間）。0 で即時可。
    TRASH_RETENTION_DAYS: int = 14
    # True のとき、退避期間経過前は permanently_delete を拒否（DB・UI 双方で有効）
    ENFORCE_TRASH_RETENTION_BEFORE_PERMANENT_DELETE: bool = True

    # UI設定
    DEFAULT_WINDOW_SIZE: Tuple[int, int] = (1300, 850)
    SIDEBAR_WIDTH: int = 240
    GALLERY_ICON_SIZE: Tuple[int, int] = (180, 180)
    GALLERY_GRID_SIZE: Tuple[int, int] = (200, 200)

    # プログレス更新間隔
    PROGRESS_UPDATE_INTERVAL_SCAN: int = 20
    PROGRESS_UPDATE_INTERVAL_ANALYZE: int = 5

    # SSD負荷軽減設定
    LOW_LOAD_MODE: bool = False
    LOW_LOAD_SLEEP_TIME: float = 0.001

    # 類似検索設定
    DEFAULT_SIMILARITY_THRESHOLD: int = 5
    MAX_SIMILARITY_DISTANCE: int = 25

    # ピンボケ検出設定
    DEFAULT_BLUR_THRESHOLD: int = 20
    MAX_BLUR_THRESHOLD: int = 50
    BLUR_LIST_LIMIT: int = 2000

    # クラスタリング設定
    MAX_CLUSTERING_IMAGES: int = 10000
    DBSCAN_EPS: float = 0.15
    DBSCAN_MIN_SAMPLES: int = 2

    # グリッドビュー設定
    DEFAULT_GRID_THUMBNAIL_SIZE: int = 160
    MIN_GRID_THUMBNAIL_SIZE: int = 80
    MAX_GRID_THUMBNAIL_SIZE: int = 300
    GRID_THUMBNAIL_STEP: int = 20

    # 小さいファイル削除設定
    MIN_FILE_SIZE_THRESHOLD: int = 10 * 1024
    MIN_IMAGE_SIZE_THRESHOLD: Tuple[int, int] = (100, 100)

    # AIモデル設定
    HF_OFFLINE_MODE: bool = False
    HF_MIRROR_SITE: Optional[str] = None
    HF_MODEL_CACHE_DIR: Optional[str] = None

    # AI設定
    CLIP_MODEL_NAME: str = "openai/clip-vit-base-patch32"
    AI_SUGGESTION_THRESHOLD: float = 0.3
    AI_CONFIDENCE_THRESHOLD: float = 0.3

    # AIカテゴリ設定
    AI_EVENT_LABELS: list = field(default_factory=lambda: [
        "ゴルフ", "バスケットボール", "野球", "サッカー", "テニス",
        "仕事_書類", "スクリーンショット",
        "食事_居酒屋", "カフェ_スイーツ", "ラーメン",
        "旅行_風景", "海_ビーチ", "山_自然", "神社_寺",
        "街並み", "乗り物", "猫_ペット", "犬_ペット",
        "集合写真", "屋内_部屋", "日常"
    ])

    # ログ設定
    LOG_FILE: str = "debug.log"
    LOG_LEVEL: str = "DEBUG"

    # セキュリティ設定
    MAX_PATH_LENGTH: int = 4096
    ALLOWED_PATH_PREFIXES: Tuple[str, ...] = ()

    def validate_path(self, path: str) -> bool:
        if not path or len(path) > self.MAX_PATH_LENGTH:
            return False
        normalized = os.path.normpath(path)
        if not os.path.isabs(path):
            if '..' in normalized or normalized.startswith('..'):
                return False
        if self.ALLOWED_PATH_PREFIXES:
            return any(path.startswith(prefix) for prefix in self.ALLOWED_PATH_PREFIXES)
        return True

    def get_default_trash_folder(self) -> str:
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "PhotoSortX_Trash")


config = AppConfig()

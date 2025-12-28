"""
設定管理モジュール
アプリケーション全体で使用する設定値を一元管理
"""
from dataclasses import dataclass
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
    
    # UI設定
    DEFAULT_WINDOW_SIZE: Tuple[int, int] = (1300, 850)
    SIDEBAR_WIDTH: int = 240
    GALLERY_ICON_SIZE: Tuple[int, int] = (180, 180)
    GALLERY_GRID_SIZE: Tuple[int, int] = (200, 200)
    
    # プログレス更新間隔
    PROGRESS_UPDATE_INTERVAL_SCAN: int = 20
    PROGRESS_UPDATE_INTERVAL_ANALYZE: int = 5
    
    # 類似検索設定
    DEFAULT_SIMILARITY_THRESHOLD: int = 5
    MAX_SIMILARITY_DISTANCE: int = 25
    
    # ピンボケ検出設定
    DEFAULT_BLUR_THRESHOLD: int = 20
    MAX_BLUR_THRESHOLD: int = 50
    
    # クラスタリング設定
    MAX_CLUSTERING_IMAGES: int = 10000  # 実用的な枚数に変更
    DBSCAN_EPS: float = 0.15
    DBSCAN_MIN_SAMPLES: int = 2
    
    # グリッドビュー設定
    DEFAULT_GRID_THUMBNAIL_SIZE: int = 160  # デフォルトサムネイルサイズ（大きく）
    MIN_GRID_THUMBNAIL_SIZE: int = 80  # 最小サムネイルサイズ
    MAX_GRID_THUMBNAIL_SIZE: int = 300  # 最大サムネイルサイズ
    GRID_THUMBNAIL_STEP: int = 20  # ホイールズーム時のステップ
    
    # 小さいファイル削除設定
    MIN_FILE_SIZE_THRESHOLD: int = 10 * 1024  # 10KB未満を削除対象（デフォルト）
    MIN_IMAGE_SIZE_THRESHOLD: Tuple[int, int] = (100, 100)  # 100x100未満の画像を削除対象（デフォルト）
    
    # AIモデル設定
    # Hugging Face接続エラー対策: オフラインモードとミラーサイト
    HF_OFFLINE_MODE: bool = False  # Trueにするとオフラインモード（既存モデルを使用）
    HF_MIRROR_SITE: Optional[str] = None  # ミラーサイトURL（例: "https://hf-mirror.com"）
    HF_MODEL_CACHE_DIR: Optional[str] = None  # モデルキャッシュディレクトリ（Noneの場合はデフォルト）
    
    # AI設定
    CLIP_MODEL_NAME: str = "openai/clip-vit-base-patch32"
    AI_SUGGESTION_THRESHOLD: float = 0.3
    
    # ログ設定
    LOG_FILE: str = "debug.log"
    LOG_LEVEL: str = "DEBUG"
    
    # セキュリティ設定
    MAX_PATH_LENGTH: int = 4096  # 一般的なOSの最大パス長
    ALLOWED_PATH_PREFIXES: Tuple[str, ...] = ()  # 空の場合は全パス許可
    
    def validate_path(self, path: str) -> bool:
        """
        パスの安全性を検証
        
        Args:
            path: 検証するパス
            
        Returns:
            安全なパスの場合True
        """
        if not path or len(path) > self.MAX_PATH_LENGTH:
            return False
        
        # パストラバーサル対策: 相対パスで親ディレクトリへの移動を検出
        # 絶対パス（Windows: D:/, C:/ など、Unix: / で始まる）は許可
        normalized = os.path.normpath(path)
        
        # 相対パスで '..' が含まれている場合は危険
        if not os.path.isabs(path):
            if '..' in normalized or normalized.startswith('..'):
                return False
        
        # 許可されたプレフィックスのチェック（設定されている場合）
        if self.ALLOWED_PATH_PREFIXES:
            return any(path.startswith(prefix) for prefix in self.ALLOWED_PATH_PREFIXES)
        
        return True
    
    def get_default_trash_folder(self) -> str:
        """
        デフォルト削除フォルダのパスを取得
        
        Returns:
            デフォルト削除フォルダのパス
        """
        # Windows: ユーザーのホームディレクトリ下に作成
        # Unix/Linux: ホームディレクトリ下に作成
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "PhotoSortX_Trash")


# グローバル設定インスタンス
config = AppConfig()


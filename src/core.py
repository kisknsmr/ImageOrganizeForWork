"""
コアモジュール
データベース管理、画像処理、スレッド処理などの主要機能を提供
"""
import sys
import os
import time
import hashlib
import logging
import traceback
from typing import Optional, List, Tuple, Set, Any
from pathlib import Path

# Image Processing
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFile

# PyQt Core
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QRunnable, QBuffer, QIODevice, QSize
from PyQt6.QtGui import QImage, QImageReader, QColor, QPixmap

# 設定（src パッケージ内）
from .config import config
from .database import DatabaseManager

ImageFile.LOAD_TRUNCATED_IMAGES = True

logger = logging.getLogger(__name__)

# 軽量ユーティリティを再エクスポート（後方互換のため）
from .utils import path_under_root, format_eta, hamming_dist, format_file_size, format_file_size_kb


def setup_logging() -> None:
    """
    ロギング設定を初期化
    
    ファイルとコンソールの両方にログを出力します。
    RotatingFileHandler でログファイルの肥大化を防止します。
    """
    from logging.handlers import RotatingFileHandler

    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.DEBUG)
    fmt = '%(asctime)s [%(levelname)s] (%(threadName)s) - %(message)s'

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return  # 重複初期化を防止

    root_logger.setLevel(log_level)

    # ファイルハンドラ（最大 5MB × 3 世代）
    file_handler = RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(fmt))
    root_logger.addHandler(file_handler)

    # コンソールハンドラ
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(fmt))
    root_logger.addHandler(console_handler)

    logging.getLogger("PIL").setLevel(logging.WARNING)


def create_error_pixmap(size: int) -> QPixmap:
    """
    エラー表示用のプレースホルダー画像を生成
    
    Args:
        size: 画像のサイズ（ピクセル）
        
    Returns:
        エラー表示用のQPixmap
    """
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor("#222222"))
    return QPixmap.fromImage(img)


def _generate_video_thumbnail(db_manager, file_id: int, file_path: str, size_wh: int) -> QPixmap:
    """
    動画ファイルの先頭フレームからサムネイルを生成。
    cv2.VideoCapture でフレームを取得し、QPixmap に変換する。
    """
    try:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return create_error_pixmap(size_wh)

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return create_error_pixmap(size_wh)

        # BGR → RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        pix = QPixmap.fromImage(q_img)
        if pix.isNull():
            return create_error_pixmap(size_wh)

        pix = pix.scaled(size_wh, size_wh, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)

        # DB にキャッシュ
        if file_id and file_id > 0:
            try:
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pix.save(buffer, "JPG", config.THUMBNAIL_QUALITY)
                db_manager.save_thumbnail(file_id, bytes(buffer.data()))
            except Exception as e:
                logger.error(f"Failed to save video thumbnail to DB (id={file_id}): {e}")

        return pix

    except Exception as e:
        logger.error(f"Failed to generate video thumbnail for {file_path}: {e}", exc_info=True)
        return create_error_pixmap(size_wh)


def get_db_thumbnail(db_manager: 'DatabaseManager', file_id: int, file_path: str,
                     size_wh: int = None) -> QPixmap:
    """
    サムネイル取得関数（縦横比保持）。
    DBにキャッシュがあればそれを返し、なければファイルから生成してDBに保存します。
    返す画像は幅・高さとも size_wh 以下に収まり、元画像の縦横比を保ちます。

    Args:
        db_manager: データベースマネージャーインスタンス
        file_id: ファイルID
        file_path: ファイルパス
        size_wh: 最大幅・高さ（デフォルト: config.DEFAULT_THUMBNAIL_SIZE）

    Returns:
        サムネイル画像のQPixmap（縦横比保持）
    """
    if size_wh is None:
        size_wh = config.DEFAULT_THUMBNAIL_SIZE
    
    # パス検証
    if not config.validate_path(file_path):
        logger.warning(f"Invalid path detected: {file_path}")
        return create_error_pixmap(size_wh)
    
    # 1. DBから取得
    if file_id and file_id > 0:
        try:
            blob = db_manager.get_thumbnail(file_id)
            if blob:
                pix = QPixmap()
                if pix.loadFromData(blob):
                    if pix.width() > size_wh or pix.height() > size_wh:
                        pix = pix.scaled(size_wh, size_wh, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                    return pix
        except Exception as e:
            logger.error(f"Failed to load thumbnail from DB (id={file_id}): {e}")

    # 2. ファイルから生成
    try:
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            return create_error_pixmap(size_wh)

        ext = os.path.splitext(file_path)[1].lower()

        # 2a. 動画の場合: cv2.VideoCapture で先頭フレームを取得
        if ext in config.VIDEO_EXTENSIONS:
            return _generate_video_thumbnail(db_manager, file_id, file_path, size_wh)

        # 2b. 画像の場合: QImageReader で読み込み
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)

        orig_size = reader.size()
        if orig_size.isValid():
            orig_size.scale(size_wh, size_wh, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(orig_size)

        img = reader.read()

        if not img.isNull():
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buffer, "JPG", quality=config.THUMBNAIL_QUALITY)
            blob_data = bytes(buffer.data())

            if file_id and file_id > 0:
                try:
                    db_manager.save_thumbnail(file_id, blob_data)
                except Exception as e:
                    logger.error(f"Failed to save thumbnail to DB (id={file_id}): {e}")

            return QPixmap.fromImage(img)

        return create_error_pixmap(size_wh)

    except (OSError, IOError) as e:
        logger.error(f"IO error while generating thumbnail ({os.path.basename(file_path)}): {e}")
        return create_error_pixmap(size_wh)
    except Exception as e:
        logger.error(f"Unexpected error while generating thumbnail ({os.path.basename(file_path)}): {e}", 
                     exc_info=True)
        return create_error_pixmap(size_wh)


def get_preview_image(file_path: str, max_size: int = 800) -> QPixmap:
    """
    プレビュー用画像取得関数
    
    元の画像比率を保ったまま、指定された最大サイズに収まるようにリサイズします。
    サムネイルとは異なり、高画質で生成し、DBにはキャッシュしません。
    
    Args:
        file_path: ファイルパス
        max_size: 最大幅/高さ（デフォルト: 800px）
        
    Returns:
        プレビュー画像のQPixmap
    """
    # パス検証
    if not config.validate_path(file_path):
        logger.warning(f"Invalid path detected: {file_path}")
        return create_error_pixmap(max_size)
    
    try:
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            return create_error_pixmap(max_size)

        ext = os.path.splitext(file_path)[1].lower()

        # 動画の場合: cv2.VideoCapture で先頭フレームを取得
        if ext in config.VIDEO_EXTENSIONS:
            return _generate_video_thumbnail(None, 0, file_path, max_size)

        reader = QImageReader(file_path)
        reader.setAutoTransform(True)

        orig_size = reader.size()
        if orig_size.isValid():
            scaled_size = orig_size.scaled(max_size, max_size, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(scaled_size)

        img = reader.read()

        if not img.isNull():
            pix = QPixmap.fromImage(img)
            return pix

        return create_error_pixmap(max_size)

    except (OSError, IOError) as e:
        logger.error(f"IO error while generating preview image ({os.path.basename(file_path)}): {e}")
        return create_error_pixmap(max_size)
    except Exception as e:
        logger.error(f"Unexpected error while generating preview image ({os.path.basename(file_path)}): {e}", 
                     exc_info=True)
        return create_error_pixmap(max_size)


# format_eta は src.utils に移動済み（後方互換のため上で再エクスポート）


def get_capture_time(path: str) -> float:
    """
    ファイルの更新日時を取得
    
    Args:
        path: ファイルパス
        
    Returns:
        更新日時（タイムスタンプ）、エラー時は0
    """
    try:
        if not config.validate_path(path):
            logger.warning(f"Invalid path for get_capture_time: {path}")
            return 0.0
        return os.path.getmtime(path)
    except (OSError, IOError) as e:
        logger.error(f"Failed to get mtime for {path}: {e}")
        return 0.0
    except Exception as e:
        logger.error(f"Unexpected error getting mtime for {path}: {e}", exc_info=True)
        return 0.0


# hamming_dist, format_file_size, format_file_size_kb は src.utils に移動済み


def get_file_info(path: str) -> dict:
    """
    ファイルの詳細情報を取得
    
    Args:
        path: ファイルパス
        
    Returns:
        ファイル情報の辞書 (exists, file_size, image_width, image_height)
    """
    result = {
        'exists': False,
        'file_size': 0,
        'image_width': None,
        'image_height': None
    }
    
    try:
        if not os.path.exists(path):
            return result
            
        result['exists'] = True
        result['file_size'] = os.path.getsize(path)
        
        # 画像サイズを取得
        try:
            from PIL import Image
            with Image.open(path) as img:
                result['image_width'] = img.width
                result['image_height'] = img.height
        except (OSError, IOError) as e:
            # 画像でない場合や読み込みエラーは無視（正常なケース）
            logger.debug(f"Could not read image dimensions for {path}: {e}")
        except Exception as e:
            # 予期しないエラーはログに記録
            logger.warning(f"Unexpected error reading image dimensions for {path}: {e}")
            
    except Exception as e:
        logger.warning(f"Failed to get file info for {path}: {e}")
        
    return result


# --- Workers ---
class ScannerThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, root, db):
        super().__init__()
        self.root = root
        self.db = db
        self.run_flag = True

    def run(self):
        start = time.time()
        try:
            self.status.emit("DB登録パスの実在確認中...")
            n_pruned = self.db.prune_missing_file_paths(include_trash=True)
            if n_pruned:
                logger.info(f"Scanner: pruned {n_pruned} missing path(s) from DB")
                self.status.emit(f"実在しないパス {n_pruned} 件をDBから削除しました。フォルダ走査を続けます…")
        except Exception as e:
            logger.error(f"Scanner: prune_missing_file_paths failed: {e}", exc_info=True)

        self.status.emit(f"フォルダ走査中: {self.root}")

        disk_files = set()
        for r, _, fs in os.walk(self.root):
            if not self.run_flag: break
            
            # ゴミ箱フォルダはスキップ
            if config.TRASH_FOLDER_NAME in r:
                continue

            for f in fs:
                ext = os.path.splitext(f)[1].lower()
                if ext in config.ALL_EXTENSIONS:
                    full_path = os.path.normpath(os.path.join(r, f))
                    if config.validate_path(full_path):
                        disk_files.add(full_path)
                    else:
                        logger.warning(f"Invalid path skipped: {full_path}")
            if len(disk_files) % 1000 == 0:
                self.status.emit(f"発見: {len(disk_files)}...")

        if not self.run_flag:
            self.finished.emit()
            return

        db_files = set(os.path.normpath(p) for p in self.db.get_all_files())
        new_files = list(disk_files - db_files)
        missing_candidates = db_files - disk_files

        # 削除するのは「今回スキャンしたルート直下のパスで、ディスクに無いもの」のみ。
        missing_files = [p for p in missing_candidates if path_under_root(p, self.root)]

        if missing_files:
            self.status.emit(f"削除同期: {len(missing_files)} 件の古い情報を削除中...")
            self.db.remove_files(missing_files)

        total = len(new_files)
        if total == 0:
            self.status.emit("最新の状態です")
            self.db.set_setting("root_path", self.root)
            self.finished.emit()
            return

        self.status.emit(f"新規 {total} 件を登録中...")
        t_start = time.time()

        for i, p in enumerate(new_files):
            if not self.run_flag: break
            try:
                st = os.stat(p)
                self.db.insert_file(p, st.st_size, get_capture_time(p))
                
                # SSD負荷軽減措置
                if config.LOW_LOAD_MODE:
                    time.sleep(config.LOW_LOAD_SLEEP_TIME)

                if i % config.PROGRESS_UPDATE_INTERVAL_SCAN == 0:
                    per = int((i / total) * 100)
                    self.progress.emit(per)
                    elap = time.time() - t_start
                    if elap > 0:
                        rem = (total - i) / (i / elap) if i > 0 else 0
                        self.status.emit(f"登録中: {i}/{total} 残り{format_eta(rem)}")
            except Exception as e:
                logger.error(f"Scanner Skip Error for {p}: {e}", exc_info=True)

        self.db.set_setting("root_path", self.root)
        self.status.emit("完了")
        self.finished.emit()

    def stop(self):
        self.run_flag = False


class AnalyzerThread(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.run_flag = True

    def calc_blur(self, p: str) -> float:
        """
        画像のピンボケスコアを計算（Laplacian分散）
        
        Args:
            p: 画像ファイルパス
            
        Returns:
            ピンボケスコア（0.0の場合はエラーまたは大きすぎるファイル）
        """
        if not config.validate_path(p):
            logger.warning(f"Invalid path for blur calculation: {p}")
            return 0.0
        
        try:
            file_size = os.path.getsize(p)
            if file_size > config.MAX_IMAGE_SIZE_FOR_ANALYSIS:
                logger.debug(f"File too large for blur calculation: {p} ({file_size} bytes)")
                return 0.0

            with open(p, "rb") as f:
                img_data = f.read()

            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if img is None:
                logger.warning(f"Failed to decode image for blur calculation: {p}")
                return 0.0

            blur_score = float(cv2.Laplacian(img, cv2.CV_64F).var())
            return blur_score
        except (OSError, IOError) as e:
            logger.error(f"IO error calculating blur for {p}: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"Unexpected error calculating blur for {p}: {e}", exc_info=True)
            return 0.0

    def calc_phash(self, p: str) -> str:
        """
        画像のパーセプチュアルハッシュを計算
        
        Args:
            p: 画像ファイルパス
            
        Returns:
            16進数のハッシュ文字列（エラー時は空文字列）
        """
        if not config.validate_path(p):
            logger.warning(f"Invalid path for phash calculation: {p}")
            return ""
        
        try:
            file_size = os.path.getsize(p)
            if file_size > config.MAX_IMAGE_SIZE_FOR_ANALYSIS:
                logger.debug(f"File too large for phash calculation: {p} ({file_size} bytes)")
                return ""

            with open(p, "rb") as f:
                img_data = f.read()

            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if img is None:
                logger.warning(f"Failed to decode image for phash calculation: {p}")
                return ""

            img_small = cv2.resize(img, config.PHASH_SIZE, interpolation=cv2.INTER_AREA)
            diff = img_small[:, 1:] > img_small[:, :-1]
            decimal_val = 0
            for i, val in enumerate(diff.flatten()):
                if val:
                    decimal_val |= 1 << (63 - i)
            return f"{decimal_val:016x}"
        except (OSError, IOError) as e:
            logger.error(f"IO error calculating phash for {p}: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error calculating phash for {p}: {e}", exc_info=True)
            return ""

    def gen_thumb(self, fid: int, path: str) -> None:
        """
        サムネイルを生成してDBに保存
        
        Args:
            fid: ファイルID
            path: ファイルパス
        """
        try:
            get_db_thumbnail(self.db, fid, path)
        except Exception as e:
            logger.error(f"Failed to generate thumbnail for file_id {fid}, path {path}: {e}")

    def run(self):
        total = self.db.get_unprocessed_count()
        if total == 0:
            self.finished.emit()
            return

        done = 0
        start = time.time()

        while self.run_flag:
            files = self.db.get_unprocessed_files(config.BATCH_SIZE_ANALYZER)
            if not files: break

            for fid, path, ext, size in files:
                if not self.run_flag: break
                
                # SSD負荷軽減措置
                if config.LOW_LOAD_MODE:
                    time.sleep(config.LOW_LOAD_SLEEP_TIME)

                if not os.path.exists(path):
                    self.db.update_analysis_result(fid, None, "", 0, 'missing')
                    done += 1
                    continue

                if size > config.MAX_FILE_SIZE_FOR_PROCESSING:
                    self.db.update_analysis_result(fid, None, "", 0, 'skipped')
                    done += 1
                    continue

                try:
                    # MD5ハッシュ計算（ファイルの先頭部分のみ）
                    md5_hash = None
                    try:
                        with open(path, 'rb') as f:
                            md5_hash = hashlib.md5(f.read(config.MD5_READ_SIZE)).hexdigest()
                    except (OSError, IOError) as e:
                        logger.warning(f"Failed to read file for MD5: {path}, error: {e}")
                    
                    blur, phash = 0.0, ""

                    if ext in config.IMAGE_EXTENSIONS:
                        blur = self.calc_blur(path)
                        phash = self.calc_phash(path)
                        self.gen_thumb(fid, path)

                    self.db.update_analysis_result(fid, md5_hash, phash, blur)

                except Exception as e:
                    logger.error(f"Analyzer Error on {path}: {e}", exc_info=True)
                    try:
                        self.db.update_analysis_result(fid, None, "", 0, 'error')
                    except Exception as db_error:
                        logger.error(f"Failed to update error status in DB: {db_error}")

                done += 1
                if done % config.PROGRESS_UPDATE_INTERVAL_ANALYZE == 0:
                    elap = time.time() - start
                    rem = (total - done) / (done / elap) if elap > 0 else 0
                    self.status.emit(f"解析中: {done}/{total} 残り{format_eta(rem)}")
                    self.progress.emit(done, total)

        self.status.emit("完了")
        self.finished.emit()

    def stop(self):
        self.run_flag = False


class FullHashThread(QThread):
    """
    完全ハッシュ計算スレッド（オプション機能）

    簡易ハッシュ（先頭 8KB MD5）で重複候補になったファイルのみを対象に、
    ファイル全体の MD5 を計算して full_hash カラムに保存する。
    """
    progress = pyqtSignal(int, int)   # (done, total)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.run_flag = True

    def run(self):
        self.status.emit("完全ハッシュ計算中…")

        # 簡易ハッシュで重複候補になっているファイルだけ取得
        files = self.db.get_files_needing_full_hash(limit=50000)
        total = len(files)

        if total == 0:
            self.status.emit("完全ハッシュ: 対象ファイルなし")
            self.finished.emit()
            return

        self.status.emit(f"完全ハッシュ: {total} 件を計算中…")
        start = time.time()

        for done, (fid, path, size) in enumerate(files, 1):
            if not self.run_flag:
                break

            if not os.path.exists(path):
                continue

            try:
                h = hashlib.md5()
                with open(path, 'rb') as f:
                    while True:
                        chunk = f.read(1024 * 1024)  # 1 MB ずつ読み込み
                        if not chunk:
                            break
                        h.update(chunk)
                self.db.update_full_hash(fid, h.hexdigest())
            except (OSError, IOError) as e:
                logger.warning(f"Full hash read error: {path}: {e}")
            except Exception as e:
                logger.error(f"Full hash error: {path}: {e}", exc_info=True)

            if done % 10 == 0 or done == total:
                elap = time.time() - start
                rem = (total - done) / (done / elap) if elap > 0 else 0
                self.status.emit(f"完全ハッシュ: {done}/{total} 残り{format_eta(rem)}")
                self.progress.emit(done, total)

        self.status.emit("完全ハッシュ: 完了")
        self.finished.emit()

    def stop(self):
        self.run_flag = False


class ImageLoader(QRunnable):
    """
    画像読み込み用のワーカークラス
    
    非同期で画像を読み込み、サムネイルを生成します。
    """
    
    def __init__(self, idx: int, path: str, size: QSize):
        """
        画像ローダーを初期化
        
        Args:
            idx: 画像のインデックス
            path: 画像ファイルパス
            size: サムネイルサイズ
        """
        super().__init__()
        self.idx = idx
        self.path = path
        self.size = size
        self.signals = ImageLoaderSignals()

    def run(self) -> None:
        """
        画像を読み込んでサムネイルを生成
        """
        if not config.validate_path(self.path):
            logger.warning(f"Invalid path for ImageLoader: {self.path}")
            error_pixmap = create_error_pixmap(self.size.width())
            error_img = error_pixmap.toImage()
            self.signals.finished.emit(self.idx, error_img)
            return

        try:
            reader = QImageReader(self.path)
            reader.setScaledSize(reader.size().scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio))
            reader.setAutoTransform(True)
            img = reader.read()

            if img.isNull():
                logger.warning(f"Failed to read image: {self.path}")
                error_pixmap = create_error_pixmap(self.size.width())
                error_img = error_pixmap.toImage()
                self.signals.finished.emit(self.idx, error_img)
            else:
                self.signals.finished.emit(self.idx, img)
        except (OSError, IOError) as e:
            logger.error(f"IO error loading image {self.path}: {e}")
            error_pixmap = create_error_pixmap(self.size.width())
            error_img = error_pixmap.toImage()
            self.signals.finished.emit(self.idx, error_img)
        except Exception as e:
            logger.error(f"Unexpected error loading image {self.path}: {e}", exc_info=True)
            error_pixmap = create_error_pixmap(self.size.width())
            error_img = error_pixmap.toImage()
            self.signals.finished.emit(self.idx, error_img)


class ImageLoaderSignals(QObject): finished = pyqtSignal(int, QImage)
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

# 設定
from config import config
from database import DatabaseManager

ImageFile.LOAD_TRUNCATED_IMAGES = True

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """
    ロギング設定を初期化
    
    ファイルとコンソールの両方にログを出力します。
    """
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.DEBUG)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] (%(threadName)s) - %(message)s',
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
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


def get_db_thumbnail(db_manager: 'DatabaseManager', file_id: int, file_path: str, 
                     size_wh: int = None) -> QPixmap:
    """
    サムネイル取得関数
    
    DBにキャッシュがあればそれを返し、なければファイルから生成してDBに保存します。
    
    Args:
        db_manager: データベースマネージャーインスタンス
        file_id: ファイルID
        file_path: ファイルパス
        size_wh: サムネイルサイズ（デフォルト: config.DEFAULT_THUMBNAIL_SIZE）
        
    Returns:
        サムネイル画像のQPixmap
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


def format_eta(seconds: float) -> str:
    """
    残り時間をフォーマット（HH:MM:SS または MM:SS）
    
    Args:
        seconds: 残り秒数
        
    Returns:
        フォーマットされた時間文字列
    """
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


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


def hamming_dist(h1: int, h2: int) -> int:
    """
    ハミング距離を計算（2つのハッシュ値の違い）
    
    Args:
        h1: 最初のハッシュ値
        h2: 2番目のハッシュ値
        
    Returns:
        ハミング距離
    """
    return (h1 ^ h2).bit_count()


def format_file_size(size_bytes: int) -> str:
    """
    ファイルサイズを人間が読みやすい形式にフォーマット
    
    Args:
        size_bytes: バイト数
        
    Returns:
        フォーマットされたサイズ文字列 (例: "1.5 MB")
    """
    if size_bytes < 0:
        return "不明"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


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
        except Exception:
            pass  # 画像でない場合は無視
            
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
        missing_files = [p for p in missing_candidates if p.startswith(os.path.normpath(self.root))]

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
                print(f"Scanner Skip Error: {e}", flush=True)

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
            
            return float(cv2.Laplacian(img, cv2.CV_64F).var())
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
            self.signals.finished.emit(self.idx, create_error_pixmap(self.size.width()))
            return
        
        try:
            reader = QImageReader(self.path)
            reader.setScaledSize(reader.size().scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio))
            reader.setAutoTransform(True)
            img = reader.read()
            
            if img.isNull():
                logger.warning(f"Failed to read image: {self.path}")
                self.signals.finished.emit(self.idx, create_error_pixmap(self.size.width()))
            else:
                self.signals.finished.emit(self.idx, img)
        except (OSError, IOError) as e:
            logger.error(f"IO error loading image {self.path}: {e}")
            self.signals.finished.emit(self.idx, create_error_pixmap(self.size.width()))
        except Exception as e:
            logger.error(f"Unexpected error loading image {self.path}: {e}", exc_info=True)
            self.signals.finished.emit(self.idx, create_error_pixmap(self.size.width()))


class ImageLoaderSignals(QObject): finished = pyqtSignal(int, QImage)
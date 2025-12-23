import sys
import os
import io
import time
import hashlib
import logging
import sqlite3
import imagehash
import shutil
import traceback
from threading import RLock
from datetime import datetime

# Image Processing
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFile

# PyQt Core
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QRunnable, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QImageReader, QColor, QPixmap

ImageFile.LOAD_TRUNCATED_IMAGES = True

logger = logging.getLogger(__name__)


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] (%(threadName)s) - %(message)s',
        handlers=[logging.FileHandler("debug.log", encoding='utf-8'), logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)


def create_error_pixmap(size):
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor("#222222"))
    return QPixmap.fromImage(img)


# ★修正: ギャラリーと同じ QImageReader を使用するロジックに変更
def get_db_thumbnail(db_manager, file_id, file_path, size_wh=120):
    # 1. DBにあればそれを返す
    blob = db_manager.get_thumbnail(file_id)
    if blob:
        pix = QPixmap()
        if pix.loadFromData(blob):
            if pix.width() > size_wh or pix.height() > size_wh:
                pix = pix.scaled(size_wh, size_wh, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            return pix

    # 2. DBになければ生成する (QImageReader使用)
    try:
        if not os.path.exists(file_path):
            return create_error_pixmap(size_wh)

        reader = QImageReader(file_path)
        reader.setAutoTransform(True)

        # メモリ保護: 読み込み時にサイズを制限
        if reader.supportsOption(QImageReader.ImageReaderOption.ScaledSize):
            new_size = reader.size()
            if new_size.isValid():
                new_size.scale(size_wh, size_wh, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(new_size)

        img = reader.read()

        if not img.isNull():
            # DB保存用にバイト列化 (PyQt6 QBuffer使用)
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buffer, "JPG", quality=70)
            blob_data = buffer.data().data()

            db_manager.save_thumbnail(file_id, blob_data)
            return QPixmap.fromImage(img)

        return create_error_pixmap(size_wh)

    except Exception:
        return create_error_pixmap(size_wh)


def format_eta(seconds):
    if seconds < 0: return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_capture_time(path):
    try:
        return os.path.getmtime(path)
    except:
        return 0


def hamming_dist(h1: int, h2: int) -> int:
    return (h1 ^ h2).bit_count()


# --- DB Manager ---
class DatabaseManager:
    def __init__(self, db_path="photos.db"):
        self.db_path = db_path
        self.lock = RLock()
        self.conn = None
        self._connect()
        self.init_db()

    def _connect(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")

    def init_db(self):
        with self.lock:
            c = self.conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, filename TEXT, extension TEXT, 
                size INTEGER, mtime TIMESTAMP, status TEXT DEFAULT 'unprocessed', 
                hash_value TEXT, p_hash TEXT, blur_score REAL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS thumbnails (
                file_id INTEGER PRIMARY KEY, data BLOB, FOREIGN KEY(file_id) REFERENCES files(id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT)''')

            c.execute('CREATE INDEX IF NOT EXISTS idx_path ON files (path)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_status ON files (status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_hash ON files (hash_value)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_mtime ON files (mtime)')
            self.conn.commit()

    def rebuild_db(self):
        with self.lock:
            try:
                if self.conn: self.conn.close()
                if os.path.exists(self.db_path):
                    try:
                        os.remove(self.db_path)
                    except:
                        pass
                for ext in ["-wal", "-shm"]:
                    p = self.db_path + ext
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except:
                            pass
                self._connect()
                self.init_db()
            except Exception as e:
                print(f"DB Rebuild Error: {e}", flush=True)
                try:
                    self._connect()
                except:
                    pass

    def set_setting(self, key, value):
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            self.conn.commit()

    def get_setting(self, key):
        with self.lock:
            try:
                row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
                return row[0] if row else None
            except:
                return None

    def save_thumbnail(self, fid, data):
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO thumbnails (file_id, data) VALUES (?, ?)", (fid, data))
            self.conn.commit()

    def get_thumbnail(self, fid):
        with self.lock:
            row = self.conn.execute("SELECT data FROM thumbnails WHERE file_id = ?", (fid,)).fetchone()
            return row[0] if row else None

    def insert_file(self, path, size, mtime):
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        try:
            with self.lock:
                c = self.conn.cursor()
                c.execute('INSERT OR IGNORE INTO files (path, filename, extension, size, mtime) VALUES (?, ?, ?, ?, ?)',
                          (path, name, ext, size, mtime))
                self.conn.commit()
                return c.rowcount > 0
        except:
            return False

    def remove_files(self, paths):
        if not paths: return
        with self.lock:
            try:
                c = self.conn.cursor()
                CHUNK_SIZE = 900
                paths_list = list(paths)
                for i in range(0, len(paths_list), CHUNK_SIZE):
                    chunk = paths_list[i:i + CHUNK_SIZE]
                    placeholders = ','.join('?' for _ in chunk)
                    c.execute(
                        f"DELETE FROM thumbnails WHERE file_id IN (SELECT id FROM files WHERE path IN ({placeholders}))",
                        chunk)
                    c.execute(f"DELETE FROM files WHERE path IN ({placeholders})", chunk)
                self.conn.commit()
            except Exception as e:
                print(f"Remove files error: {e}")

    def get_file_count(self):
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def get_unprocessed_count(self):
        with self.lock: return self.conn.execute("SELECT COUNT(*) FROM files WHERE status = 'unprocessed'").fetchone()[
            0]

    def get_unprocessed_files(self, limit=1000):
        with self.lock: return self.conn.execute(
            "SELECT id, path, extension, size FROM files WHERE status = 'unprocessed' LIMIT ?", (limit,)).fetchall()

    def update_analysis_result(self, fid, md5, phash, blur, status='analyzed'):
        with self.lock:
            self.conn.execute('UPDATE files SET hash_value=?, p_hash=?, blur_score=?, status=? WHERE id=?',
                              (md5, phash, blur, status, fid))
            self.conn.commit()

    def get_duplicate_hashes(self):
        with self.lock:
            return self.conn.execute(
                'SELECT hash_value, COUNT(*) as cnt FROM files WHERE hash_value IS NOT NULL AND status != "trash" GROUP BY hash_value HAVING cnt > 1 ORDER BY cnt DESC').fetchall()

    def get_files_by_hash(self, val):
        with self.lock: return self.conn.execute(
            "SELECT id, path, size, mtime FROM files WHERE hash_value = ? AND status != 'trash'", (val,)).fetchall()

    def get_blurry_files(self, th):
        with self.lock: return self.conn.execute(
            'SELECT id, path FROM files WHERE blur_score > 0 AND blur_score < ? AND status != "trash" ORDER BY blur_score ASC LIMIT 200',
            (th,)).fetchall()

    def get_files_with_phash(self):
        with self.lock: return self.conn.execute(
            "SELECT id, path, p_hash, mtime FROM files WHERE p_hash IS NOT NULL AND status != 'trash'").fetchall()

    def get_all_files(self):
        with self.lock:
            return [r[0] for r in
                    self.conn.execute("SELECT path FROM files WHERE status != 'trash' ORDER BY mtime DESC").fetchall()]

    def get_analyzed_files_unsorted(self, limit=100):
        with self.lock: return self.conn.execute("SELECT id, path, p_hash FROM files WHERE status = 'analyzed' LIMIT ?",
                                                 (limit,)).fetchall()

    def move_file_to_folder(self, fid, src, folder):
        try:
            name = os.path.basename(src)
            dest = os.path.join(folder, name)
            if os.path.abspath(os.path.dirname(src)) == os.path.abspath(folder): return True
            if os.path.exists(dest):
                base, ext = os.path.splitext(name)
                dest = os.path.join(folder, f"{base}_{int(time.time())}{ext}")
            shutil.move(src, dest)
            with self.lock:
                self.conn.execute("UPDATE files SET path = ?, status = 'sorted' WHERE id = ?", (dest, fid))
                self.conn.commit()
            return True
        except Exception as e:
            print(f"Move Error: {e}", flush=True)
            return False

    def move_to_trash(self, fid):
        with self.lock:
            row = self.conn.execute("SELECT path FROM files WHERE id = ?", (fid,)).fetchone()
            path = row[0] if row else None
            success = False
            if path:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        success = True
                    except:
                        pass
                else:
                    success = True
            if success:
                self.conn.execute("UPDATE files SET status = 'trash' WHERE id = ?", (fid,))
                self.conn.commit()
                return True
            return False

    def close(self):
        if self.conn: self.conn.close()


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
            for f in fs:
                if os.path.splitext(f)[1].lower() in {'.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov', '.webp'}:
                    disk_files.add(os.path.normpath(os.path.join(r, f)))
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

                if i % 20 == 0:
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

    def calc_blur(self, p):
        try:
            if os.path.getsize(p) > 50 * 1024 * 1024: return 0.0

            img_data = open(p, "rb").read()
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if img is None: return 0.0
            return float(cv2.Laplacian(img, cv2.CV_64F).var())
        except Exception as e:
            print(f"Blur calc error on {p}: {e}", flush=True)
            return 0.0

    def calc_phash(self, p):
        try:
            if os.path.getsize(p) > 50 * 1024 * 1024: return ""

            img_data = open(p, "rb").read()
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if img is None: return ""

            img_small = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA)
            diff = img_small[:, 1:] > img_small[:, :-1]
            decimal_val = 0
            for i, val in enumerate(diff.flatten()):
                if val:
                    decimal_val |= 1 << (63 - i)
            return f"{decimal_val:016x}"
        except Exception as e:
            print(f"Phash calc error on {p}: {e}", flush=True)
            return ""

    def gen_thumb(self, fid, path):
        try:
            get_db_thumbnail(self.db, fid, path)
        except:
            pass

    def run(self):
        total = self.db.get_unprocessed_count()
        if total == 0:
            self.finished.emit()
            return

        done = 0
        start = time.time()

        while self.run_flag:
            files = self.db.get_unprocessed_files(20)
            if not files: break

            for fid, path, ext, size in files:
                if not self.run_flag: break

                if not os.path.exists(path):
                    self.db.update_analysis_result(fid, None, "", 0, 'missing')
                    done += 1
                    continue

                if size > 100 * 1024 * 1024:
                    self.db.update_analysis_result(fid, None, "", 0, 'skipped')
                    done += 1
                    continue

                try:
                    md5 = hashlib.md5(open(path, 'rb').read(8192)).hexdigest()
                    blur, phash = 0.0, ""

                    if ext in {'.jpg', '.jpeg', '.png', '.webp', '.heic'}:
                        blur = self.calc_blur(path)
                        phash = self.calc_phash(path)
                        self.gen_thumb(fid, path)

                    self.db.update_analysis_result(fid, md5, phash, blur)

                except Exception as e:
                    print(f"Analyzer Error on {path}: {e}", flush=True)
                    self.db.update_analysis_result(fid, None, "", 0, 'error')

                done += 1

                if done % 5 == 0:
                    elap = time.time() - start
                    rem = (total - done) / (done / elap) if elap > 0 else 0
                    self.status.emit(f"解析中: {done}/{total} 残り{format_eta(rem)}")
                    self.progress.emit(done, total)

        self.status.emit("完了")
        self.finished.emit()

    def stop(self):
        self.run_flag = False


class ImageLoader(QRunnable):
    def __init__(self, idx, path, size):
        super().__init__();
        self.idx = idx;
        self.path = path;
        self.size = size;
        self.signals = ImageLoaderSignals()

    def run(self):
        try:
            r = QImageReader(self.path);
            r.setScaledSize(r.size().scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio));
            r.setAutoTransform(True)
            self.signals.finished.emit(self.idx, r.read())
        except:
            self.signals.finished.emit(self.idx, create_error_pixmap(self.size.width()))


class ImageLoaderSignals(QObject): finished = pyqtSignal(int, QImage)
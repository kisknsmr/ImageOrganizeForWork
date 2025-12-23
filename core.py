import sys
import os
import io
import time
import hashlib
import logging
import sqlite3
import imagehash
from threading import Lock
from collections import defaultdict
from datetime import datetime

# Image Processing
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFile
from PIL.ExifTags import TAGS

# PyQt Core
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QRunnable
from PyQt6.QtGui import QImage, QImageReader, QColor, QPixmap

ImageFile.LOAD_TRUNCATED_IMAGES = True


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] (%(threadName)s) - %(message)s',
        handlers=[logging.FileHandler("debug.log", encoding='utf-8'), logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


def create_error_pixmap(size):
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor("#444444"))
    return QPixmap.fromImage(img)


def get_db_thumbnail(db_manager, file_id, file_path, size_wh=120):
    blob = db_manager.get_thumbnail(file_id)
    if blob:
        pix = QPixmap()
        if pix.loadFromData(blob):
            if pix.width() > size_wh or pix.height() > size_wh:
                pix = pix.scaled(size_wh, size_wh, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            return pix
    try:
        if not os.path.exists(file_path): return create_error_pixmap(size_wh)
        with Image.open(file_path) as img:
            if img.mode not in ('RGB', 'RGBA'): img = img.convert('RGB')
            img = ImageOps.exif_transpose(img)
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70)
            blob_data = buffer.getvalue()
            db_manager.save_thumbnail(file_id, blob_data)
            pix = QPixmap()
            pix.loadFromData(blob_data)
            return pix.scaled(size_wh, size_wh, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    except:
        return create_error_pixmap(size_wh)


def format_eta(seconds):
    if seconds < 0: return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_capture_time(path):
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in {'.jpg', '.jpeg', '.heic', '.tiff'}:
            with Image.open(path) as img:
                exif = img.getexif()
                if exif:
                    date_str = exif.get(36867)
                    if date_str:
                        dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                        return dt.timestamp()
    except:
        pass
    return os.path.getmtime(path)


def hamming_dist(h1: int, h2: int) -> int:
    return (h1 ^ h2).bit_count()


# --- DB Manager ---
class DatabaseManager:
    def __init__(self, db_path="photos.db"):
        self.db_path = db_path
        self.lock = Lock()
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
            c.execute('CREATE INDEX IF NOT EXISTS idx_path ON files (path)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_status ON files (status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_hash ON files (hash_value)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_mtime ON files (mtime)')
            self.conn.commit()

    def rebuild_db(self):
        with self.lock:
            self.conn.cursor().execute("DROP TABLE IF EXISTS thumbnails")
            self.conn.cursor().execute("DROP TABLE IF EXISTS files")
            self.conn.commit()
            self.init_db()

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

    def get_sorted_files(self, limit=100, offset=0):
        with self.lock:
            return self.conn.execute(
                "SELECT id, path, mtime FROM files WHERE status = 'analyzed' ORDER BY mtime ASC LIMIT ? OFFSET ?",
                (limit, offset)).fetchall()

    def find_suggested_folders(self, target_phash_str, max_dist=12):
        if not target_phash_str: return []
        try:
            target_int = int(target_phash_str, 16)
        except:
            return []
        suggestions = defaultdict(int)
        with self.lock:
            rows = self.conn.execute(
                "SELECT path, p_hash FROM files WHERE p_hash IS NOT NULL AND status != 'trash'").fetchall()
        for path, phash in rows:
            try:
                dist = hamming_dist(target_int, int(phash, 16))
                if dist <= max_dist:
                    suggestions[os.path.dirname(path)] += (15 - dist)
            except:
                pass
        return [f[0] for f in sorted(suggestions.items(), key=lambda x: x[1], reverse=True)[:5]]

    def move_file_to_folder(self, fid, src, folder):
        try:
            name = os.path.basename(src)
            dest = os.path.join(folder, name)
            if os.path.abspath(os.path.dirname(src)) == os.path.abspath(folder): return True
            if os.path.exists(dest):
                base, ext = os.path.splitext(name)
                dest = os.path.join(folder, f"{base}_{int(time.time())}{ext}")
            os.rename(src, dest)
            with self.lock:
                self.conn.execute("UPDATE files SET path = ?, status = 'sorted' WHERE id = ?", (dest, fid))
                self.conn.commit()
            return True
        except:
            return False

    def move_to_trash(self, fid):
        with self.lock:
            self.conn.execute("UPDATE files SET status = 'trash' WHERE id = ?", (fid,))
            self.conn.commit()
            return True

    def close(self):
        if self.conn: self.conn.close()


# --- Workers ---
class ScannerThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, root, db):
        super().__init__(); self.root = root; self.db = db; self.run_flag = True

    def run(self):
        start = time.time()
        self.status.emit("フォルダ走査中...")
        real = set()
        for r, _, fs in os.walk(self.root):
            if not self.run_flag: break
            for f in fs:
                if os.path.splitext(f)[1].lower() in {'.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov'}:
                    real.add(os.path.normpath(os.path.join(r, f)))
            if len(real) % 1000 == 0: self.status.emit(f"発見: {len(real)}")

        db_files = set(os.path.normpath(p) for p in self.db.get_all_files())
        new_files = list(real - db_files)
        total = len(new_files)
        if total == 0: self.finished.emit(); return

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
            except:
                pass
        self.status.emit("完了")
        self.finished.emit()

    def stop(self):
        self.run_flag = False


class AnalyzerThread(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, db):
        super().__init__(); self.db = db; self.run_flag = True

    def run(self):
        total = self.db.get_unprocessed_count()
        if total == 0: self.finished.emit(); return
        done = 0
        start = time.time()
        while self.run_flag:
            files = self.db.get_unprocessed_files(20)
            if not files: break
            for fid, path, ext, size in files:
                if not self.run_flag: break
                if not os.path.exists(path):
                    self.db.update_analysis_result(fid, None, "", 0, 'missing');
                    done += 1;
                    continue
                try:
                    md5 = hashlib.md5(open(path, 'rb').read(8192)).hexdigest()
                    blur, phash = 0.0, ""
                    if ext in {'.jpg', '.jpeg', '.png', '.heic'}:
                        blur = self.calc_blur(path)
                        phash = self.calc_phash(path)
                        self.gen_thumb(fid, path)
                    self.db.update_analysis_result(fid, md5, phash, blur)
                except:
                    self.db.update_analysis_result(fid, None, "", 0, 'error')
                done += 1
                if done % 5 == 0:
                    elap = time.time() - start
                    rem = (total - done) / (done / elap) if elap > 0 else 0
                    self.status.emit(f"解析中: {done}/{total} 残り{format_eta(rem)}")
                    self.progress.emit(done, total)
        self.status.emit("完了");
        self.finished.emit()

    def gen_thumb(self, fid, path):
        try:
            img = Image.open(path).convert('RGB')
            img = ImageOps.exif_transpose(img)
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            b = io.BytesIO();
            img.save(b, "JPEG");
            self.db.save_thumbnail(fid, b.getvalue())
        except:
            pass

    def calc_blur(self, p):
        try:
            b = bytearray(open(p, "rb").read())
            n = np.asarray(b, dtype=np.uint8)
            i = cv2.imdecode(n, cv2.IMREAD_GRAYSCALE)
            return float(cv2.Laplacian(i, cv2.CV_64F).var())
        except:
            return 0.0

    def calc_phash(self, p):
        try:
            return str(imagehash.dhash(Image.open(p)))
        except:
            return ""

    def stop(self):
        self.run_flag = False


class ImageLoader(QRunnable):
    def __init__(self, idx, path, size):
        super().__init__(); self.idx = idx; self.path = path; self.size = size; self.signals = ImageLoaderSignals()

    def run(self):
        try:
            r = QImageReader(self.path);
            r.setScaledSize(r.size().scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio));
            r.setAutoTransform(True)
            self.signals.finished.emit(self.idx, r.read())
        except:
            self.signals.finished.emit(self.idx, create_error_pixmap(self.size.width()))


class ImageLoaderSignals(QObject): finished = pyqtSignal(int, QImage)
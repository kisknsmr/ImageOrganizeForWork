import sqlite3
import logging
import math
import os
import shutil
import time
from threading import RLock
from datetime import datetime
from typing import Optional, List, Tuple, Set, Any

from src.config import config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    データベース管理クラス
    SQLiteデータベースを使用して画像ファイルのメタデータとサムネイルを管理します。
    スレッドセーフな実装です。
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_NAME
        self.lock = RLock()
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self.init_db()

    def _connect(self) -> None:
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            if config.DB_WAL_MODE:
                self.conn.execute("PRAGMA journal_mode=WAL")
            # パフォーマンス最適化
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA cache_size=-16000")   # 16MB キャッシュ
            self.conn.execute("PRAGMA temp_store=MEMORY")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database {self.db_path}: {e}")
            raise

    def init_db(self) -> None:
        with self.lock:
            try:
                c = self.conn.cursor()
                c.execute('''CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, filename TEXT, extension TEXT,
                    size INTEGER, mtime TIMESTAMP, status TEXT DEFAULT 'unprocessed',
                    hash_value TEXT, p_hash TEXT, blur_score REAL)''')
                c.execute('''CREATE TABLE IF NOT EXISTS thumbnails (
                    file_id INTEGER PRIMARY KEY, data BLOB, FOREIGN KEY(file_id) REFERENCES files(id))''')
                c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT)''')
                c.execute('''CREATE TABLE IF NOT EXISTS custom_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_name TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 1,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_category_name ON custom_categories (category_name)')
                logger.info("Database: custom_categories table initialized")
                c.execute('CREATE INDEX IF NOT EXISTS idx_path ON files (path)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_status ON files (status)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_hash ON files (hash_value)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_mtime ON files (mtime)')
                # マイグレーション: full_hash カラムを追加（既存 DB 対応）
                self._migrate_add_column(c, 'files', 'full_hash', 'TEXT')
                c.execute('CREATE INDEX IF NOT EXISTS idx_full_hash ON files (full_hash)')
                # ゴミ箱に移した時刻（Unix 秒）。退避期間経過前の完全削除を防ぐ
                self._migrate_add_column(c, 'files', 'trashed_at', 'REAL')
                # トリアージ結果（keep/discard/skip）。未トリアージは NULL
                self._migrate_add_column(c, 'files', 'triage_status', 'TEXT')
                c.execute('CREATE INDEX IF NOT EXISTS idx_triage_status ON files (triage_status)')
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to initialize database: {e}")
                raise

    @staticmethod
    def _migrate_add_column(cursor, table: str, column: str, col_type: str) -> None:
        """既存テーブルにカラムが存在しなければ追加する"""
        try:
            cols = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
            if column not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info(f"Migration: added column '{column}' to '{table}'")
        except sqlite3.Error as e:
            logger.warning(f"Migration failed for {table}.{column}: {e}")

    def rebuild_db(self) -> None:
        with self.lock:
            try:
                if self.conn:
                    try:
                        self.conn.close()
                    except sqlite3.Error as e:
                        logger.warning(f"Error closing connection: {e}")
                db_files = [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]
                for db_file in db_files:
                    if os.path.exists(db_file):
                        try:
                            os.remove(db_file)
                        except (OSError, IOError) as e:
                            logger.error(f"Failed to remove database file {db_file}: {e}")
                            raise
                self._connect()
                self.init_db()
                logger.info("Database rebuilt successfully")
            except Exception as e:
                logger.error(f"DB Rebuild Error: {e}", exc_info=True)
                try:
                    self._connect()
                except Exception as reconnect_error:
                    logger.error(f"Failed to reconnect after rebuild error: {reconnect_error}")
                    raise

    def set_setting(self, key: str, value: Any) -> None:
        with self.lock:
            try:
                self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to set setting {key}: {e}")
                raise

    def get_setting(self, key: str) -> Optional[str]:
        with self.lock:
            try:
                row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
                return row[0] if row else None
            except sqlite3.Error as e:
                logger.error(f"Failed to get setting {key}: {e}")
                return None

    def get_trash_folder(self) -> Optional[str]:
        return self.get_setting("trash_folder")

    def set_trash_folder(self, path: str) -> None:
        self.set_setting("trash_folder", path)

    def save_thumbnail(self, fid: int, data: bytes) -> None:
        with self.lock:
            try:
                self.conn.execute("INSERT OR REPLACE INTO thumbnails (file_id, data) VALUES (?, ?)", (fid, data))
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to save thumbnail for file_id {fid}: {e}")

    def get_thumbnail(self, fid: int) -> Optional[bytes]:
        with self.lock:
            try:
                row = self.conn.execute("SELECT data FROM thumbnails WHERE file_id = ?", (fid,)).fetchone()
                return row[0] if row else None
            except sqlite3.Error as e:
                logger.error(f"Failed to get thumbnail for file_id {fid}: {e}")
                return None

    def insert_file(self, path: str, size: int, mtime: float) -> bool:
        if not config.validate_path(path):
            logger.warning(f"Invalid path for insert_file: {path}")
            return False
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        try:
            with self.lock:
                c = self.conn.cursor()
                c.execute('INSERT OR IGNORE INTO files (path, filename, extension, size, mtime) VALUES (?, ?, ?, ?, ?)',
                          (path, name, ext, size, mtime))
                self.conn.commit()
                return c.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to insert file {path}: {e}")
            return False

    def remove_files(self, paths: Set[str]) -> None:
        if not paths:
            return
        valid_paths = [p for p in paths if config.validate_path(p)]
        if len(valid_paths) != len(paths):
            logger.warning(f"Some paths were invalid and skipped: {len(paths) - len(valid_paths)} paths")
        with self.lock:
            try:
                c = self.conn.cursor()
                paths_list = list(valid_paths)
                for i in range(0, len(paths_list), config.BATCH_SIZE_DELETE):
                    chunk = paths_list[i:i + config.BATCH_SIZE_DELETE]
                    placeholders = ','.join('?' for _ in chunk)
                    c.execute(
                        f"DELETE FROM thumbnails WHERE file_id IN (SELECT id FROM files WHERE path IN ({placeholders}))",
                        chunk)
                    c.execute(f"DELETE FROM files WHERE path IN ({placeholders})", chunk)
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to remove files: {e}")
                raise

    def prune_missing_file_paths(self, include_trash: bool = True) -> int:
        """
        DB に登録されたパスについて、ディスク上に実在しない行を削除する（全件チェック）。
        エクスプローラ等でファイルを移動・削除したあとのゴースト行を除去する。

        Args:
            include_trash: True のとき status='trash' の行も対象（実体が消えたゴミ箱行を除去）

        Returns:
            削除した行の件数。

        Note:
            NAS 等が一時的にオフラインのとき、存在しないと誤判定され行が消える可能性がある。
        """
        with self.lock:
            if include_trash:
                rows = self.conn.execute("SELECT id, path FROM files").fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT id, path FROM files WHERE status != 'trash'"
                ).fetchall()

        missing_paths: Set[str] = set()
        invalid_ids: List[int] = []

        for i, (fid, path) in enumerate(rows):
            if not path or not str(path).strip():
                invalid_ids.append(fid)
                continue
            if not config.validate_path(path):
                invalid_ids.append(fid)
                continue
            norm = os.path.normpath(path)
            try:
                if not os.path.exists(norm):
                    missing_paths.add(path)
            except OSError as e:
                logger.warning(f"prune_missing_file_paths: exists check failed for {path}: {e}")
                missing_paths.add(path)

            if config.LOW_LOAD_MODE and (i + 1) % 1000 == 0:
                time.sleep(config.LOW_LOAD_SLEEP_TIME)

        removed = 0
        for fid in invalid_ids:
            if self.delete_file_record(fid):
                removed += 1

        if missing_paths:
            self.remove_files(missing_paths)
            removed += len(missing_paths)

        if removed:
            logger.info(f"prune_missing_file_paths: removed {removed} stale row(s)")
        return removed

    def get_file_count(self) -> int:
        with self.lock:
            try:
                return self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Failed to get file count: {e}")
                return 0

    def get_unprocessed_count(self) -> int:
        with self.lock:
            try:
                return self.conn.execute("SELECT COUNT(*) FROM files WHERE status = 'unprocessed'").fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Failed to get unprocessed count: {e}")
                return 0

    def get_unprocessed_files(self, limit: int = 1000) -> List[Tuple[int, str, str, int]]:
        with self.lock:
            try:
                return self.conn.execute(
                    "SELECT id, path, extension, size FROM files WHERE status = 'unprocessed' LIMIT ?",
                    (limit,)).fetchall()
            except sqlite3.Error as e:
                logger.error(f"Failed to get unprocessed files: {e}")
                return []

    @staticmethod
    def _content_type_for_extension(extension: str) -> str:
        ext = (extension or "").lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext in config.VIDEO_EXTENSIONS:
            return "video"
        return "image"

    def _row_to_file_dict(self, row: Tuple) -> dict:
        (fid, path, filename, extension, size, mtime, status, hash_value, p_hash,
         blur_score, full_hash, trashed_at, triage_status) = row
        return {
            "id": fid,
            "path": path,
            "filename": filename,
            "extension": extension,
            "size": size,
            "mtime": mtime,
            "status": status,
            "hash_value": hash_value,
            "p_hash": p_hash,
            "blur_score": blur_score,
            "full_hash": full_hash,
            "quality_score": None,
            "content_type": self._content_type_for_extension(extension),
            "triage_status": triage_status,
            "is_best_in_group": False,
            "scan_phase": None,
        }

    _FILE_COLUMNS = (
        "id, path, filename, extension, size, mtime, status, hash_value, p_hash, "
        "blur_score, full_hash, trashed_at, triage_status"
    )

    def get_file_by_id(self, fid: int) -> Optional[dict]:
        with self.lock:
            try:
                row = self.conn.execute(
                    f"SELECT {self._FILE_COLUMNS} FROM files WHERE id = ?", (fid,)
                ).fetchone()
            except sqlite3.Error as e:
                logger.error(f"Failed to get file by id {fid}: {e}")
                return None
        return self._row_to_file_dict(row) if row else None

    def get_library_stats(self) -> dict:
        with self.lock:
            try:
                total = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                analyzed = self.conn.execute(
                    "SELECT COUNT(*) FROM files WHERE status NOT IN ('unprocessed', 'trash')"
                ).fetchone()[0]
                unprocessed = self.conn.execute(
                    "SELECT COUNT(*) FROM files WHERE status = 'unprocessed'"
                ).fetchone()[0]
                triaged = self.conn.execute(
                    "SELECT COUNT(*) FROM files WHERE triage_status IS NOT NULL"
                ).fetchone()[0]
                trashed = self.conn.execute(
                    "SELECT COUNT(*) FROM files WHERE status = 'trash'"
                ).fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Failed to get library stats: {e}")
                return {"total": 0, "analyzed": 0, "unprocessed": 0, "triaged": 0, "trashed": 0, "root_path": None}
        return {
            "total": total,
            "analyzed": analyzed,
            "unprocessed": unprocessed,
            "triaged": triaged,
            "trashed": trashed,
            "root_path": self.get_setting("root_path"),
        }

    def get_files_page(
        self,
        page: int = 1,
        limit: int = 100,
        triage_status: Optional[str] = None,
        include_trash: bool = False,
        content_type: Optional[str] = None,
        status: Optional[str] = None,
        untriaged_only: bool = False,
    ) -> dict:
        clauses: List[str] = []
        params: List[Any] = []
        if not include_trash:
            clauses.append("status != 'trash'")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if triage_status:
            clauses.append("triage_status = ?")
            params.append(triage_status)
        if untriaged_only:
            clauses.append("triage_status IS NULL")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.lock:
            try:
                total = self.conn.execute(
                    f"SELECT COUNT(*) FROM files {where_sql}", params
                ).fetchone()[0]
                rows = self.conn.execute(
                    f"SELECT {self._FILE_COLUMNS} FROM files {where_sql} "
                    f"ORDER BY id ASC LIMIT ? OFFSET ?",
                    (*params, limit, (page - 1) * limit),
                ).fetchall()
            except sqlite3.Error as e:
                logger.error(f"Failed to get files page: {e}")
                return {"page": page, "limit": limit, "total": 0, "items": []}
        items = [self._row_to_file_dict(row) for row in rows]
        if content_type:
            items = [item for item in items if item["content_type"] == content_type]
        return {"page": page, "limit": limit, "total": total, "items": items}

    def get_next_triage_file(self, after_id: int = 0) -> Optional[dict]:
        with self.lock:
            try:
                row = self.conn.execute(
                    f"SELECT {self._FILE_COLUMNS} FROM files "
                    "WHERE id > ? AND status != 'trash' AND triage_status IS NULL "
                    "ORDER BY id ASC LIMIT 1",
                    (after_id,),
                ).fetchone()
            except sqlite3.Error as e:
                logger.error(f"Failed to get next triage file after {after_id}: {e}")
                return None
        return self._row_to_file_dict(row) if row else None

    def update_triage_status(self, fid: int, action: Optional[str]) -> bool:
        if action is not None and action not in {"keep", "discard", "skip"}:
            return False
        with self.lock:
            try:
                cur = self.conn.execute(
                    "UPDATE files SET triage_status = ? WHERE id = ?", (action, fid)
                )
                self.conn.commit()
                return cur.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Failed to update triage status for {fid}: {e}")
                return False

    def batch_update_triage_status(self, items: List[Tuple[int, Optional[str]]]) -> int:
        updated = 0
        for fid, action in items:
            if self.update_triage_status(fid, action):
                updated += 1
        return updated

    def update_analysis_result(self, fid: int, md5: Optional[str], phash: Optional[str],
                               blur: float, status: str = 'analyzed') -> None:
        with self.lock:
            try:
                self.conn.execute('UPDATE files SET hash_value=?, p_hash=?, blur_score=?, status=? WHERE id=?',
                                  (md5, phash, blur, status, fid))
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to update analysis result for file_id {fid}: {e}")
                raise

    def get_duplicate_hashes(self, use_full_hash: bool = False):
        """重複ハッシュグループを取得。use_full_hash=True のとき完全ハッシュで比較"""
        col = 'full_hash' if use_full_hash else 'hash_value'
        with self.lock:
            return self.conn.execute(
                f'SELECT {col}, COUNT(*) as cnt FROM files '
                f'WHERE {col} IS NOT NULL AND status != "trash" '
                f'GROUP BY {col} HAVING cnt > 1 ORDER BY cnt DESC').fetchall()

    def get_files_by_hash(self, val, use_full_hash: bool = False):
        """指定ハッシュ値に一致するファイル一覧を取得"""
        col = 'full_hash' if use_full_hash else 'hash_value'
        with self.lock:
            return self.conn.execute(
                f"SELECT id, path, size, mtime FROM files WHERE {col} = ? AND status != 'trash'", (val,)).fetchall()

    def update_full_hash(self, fid: int, full_hash: str) -> None:
        """完全ハッシュ値を個別に更新"""
        with self.lock:
            try:
                self.conn.execute('UPDATE files SET full_hash=? WHERE id=?', (full_hash, fid))
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to update full_hash for file_id {fid}: {e}")

    def get_files_needing_full_hash(self, limit: int = 500) -> List[Tuple[int, str, int]]:
        """完全ハッシュが未計算かつ簡易重複候補のファイル一覧を取得"""
        with self.lock:
            return self.conn.execute(
                "SELECT id, path, size FROM files "
                "WHERE full_hash IS NULL AND hash_value IS NOT NULL AND status != 'trash' "
                "AND hash_value IN ("
                "  SELECT hash_value FROM files "
                "  WHERE hash_value IS NOT NULL AND status != 'trash' "
                "  GROUP BY hash_value HAVING COUNT(*) > 1"
                ") ORDER BY size ASC LIMIT ?", (limit,)).fetchall()

    def clear_full_hashes(self) -> None:
        """全ファイルの full_hash をクリア"""
        with self.lock:
            try:
                self.conn.execute("UPDATE files SET full_hash = NULL")
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to clear full hashes: {e}")

    def get_blurry_files(self, th):
        limit = config.BLUR_LIST_LIMIT
        # 動画ファイルを除外（blur_score=0 のまま登録されるため）
        video_exts = tuple(config.VIDEO_EXTENSIONS)
        placeholders = ','.join('?' for _ in video_exts)
        with self.lock:
            rows = self.conn.execute(
                f'SELECT id, path, blur_score FROM files '
                f'WHERE blur_score > 0 AND blur_score < ? AND status != "trash" '
                f'AND extension NOT IN ({placeholders}) '
                f'ORDER BY blur_score ASC LIMIT ?',
                (th, *video_exts, limit)).fetchall()
            return [(r[0], r[1]) for r in rows]

    def get_small_files(self, max_size: int, limit: int = 5000):
        """指定サイズ未満（バイト）のゴミ箱以外ファイルを (id, path, size) で返す。"""
        with self.lock:
            try:
                rows = self.conn.execute(
                    "SELECT id, path, size FROM files "
                    "WHERE size < ? AND status != 'trash' "
                    "ORDER BY size ASC LIMIT ?",
                    (int(max_size), int(limit))).fetchall()
                return [(r[0], r[1], r[2]) for r in rows]
            except sqlite3.Error as e:
                logger.error(f"get_small_files error: {e}")
                return []

    def get_files_with_phash(self):
        with self.lock:
            return self.conn.execute(
                "SELECT id, path, p_hash, mtime, size FROM files WHERE p_hash IS NOT NULL AND status != 'trash'").fetchall()

    def get_all_files(self):
        with self.lock:
            return [r[0] for r in
                    self.conn.execute("SELECT path FROM files WHERE status != 'trash' ORDER BY mtime DESC").fetchall()]

    def get_all_files_with_info(self):
        with self.lock:
            rows = self.conn.execute("SELECT id, path, mtime FROM files WHERE status != 'trash' ORDER BY mtime ASC").fetchall()
            return [{'id': r[0], 'path': r[1], 'timestamp': r[2]} for r in rows]

    def get_files_in_folder(self, folder: str) -> List[Tuple[int, str, int, float]]:
        """指定フォルダ直下のファイルを取得 (id, path, size, mtime)"""
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, path, size, mtime FROM files WHERE status != 'trash' ORDER BY mtime DESC"
            ).fetchall()
            folder_norm = os.path.normpath(folder)
            return [(r[0], r[1], r[2], r[3]) for r in rows
                    if os.path.normpath(os.path.dirname(r[1])) == folder_norm]

    def get_folder_tree(self) -> dict:
        """全ファイルのパスからフォルダツリー構造を構築する"""
        with self.lock:
            rows = self.conn.execute(
                "SELECT path FROM files WHERE status != 'trash'"
            ).fetchall()
        # フォルダ → ファイル数をカウント
        folder_counts: dict = {}
        for (path,) in rows:
            d = os.path.normpath(os.path.dirname(path))
            folder_counts[d] = folder_counts.get(d, 0) + 1
        return folder_counts

    def get_analyzed_files_unsorted(self, limit=100):
        with self.lock:
            return self.conn.execute("SELECT id, path, p_hash FROM files WHERE status = 'analyzed' LIMIT ?", (limit,)).fetchall()

    def connect(self):
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            logger.debug(f"Created new database connection: {self.db_path}")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating database connection: {e}", exc_info=True)
            return None

    def move_file_to_folder(self, fid: int, src: str, folder: str) -> bool:
        if not config.validate_path(src) or not config.validate_path(folder):
            logger.warning(f"Invalid path for move_file_to_folder: src={src}, folder={folder}")
            return False
        try:
            name = os.path.basename(src)
            dest = os.path.join(folder, name)
            if os.path.abspath(os.path.dirname(src)) == os.path.abspath(folder):
                return True
            if os.path.exists(dest):
                base, ext = os.path.splitext(name)
                dest = os.path.join(folder, f"{base}_{int(time.time())}{ext}")
            shutil.move(src, dest)
            with self.lock:
                try:
                    self.conn.execute(
                        "UPDATE files SET path = ?, status = 'sorted', trashed_at = NULL WHERE id = ?",
                        (dest, fid),
                    )
                    self.conn.commit()
                except sqlite3.Error as db_error:
                    logger.error(f"Failed to update DB after file move: {db_error}")
                    return False
            return True
        except (OSError, IOError, shutil.Error) as e:
            logger.error(f"Failed to move file {src} to {folder}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error moving file {src} to {folder}: {e}", exc_info=True)
            return False

    def move_to_trash(self, fid: int) -> bool:
        with self.lock:
            try:
                row = self.conn.execute("SELECT path FROM files WHERE id = ?", (fid,)).fetchone()
                if not row:
                    logger.warning(f"File not found in database: id={fid}")
                    return False
                src_path = row[0]
                if not config.validate_path(src_path):
                    logger.warning(f"Invalid path for move_to_trash: {src_path}")
                    return False
                if not os.path.exists(src_path):
                    now_ts = time.time()
                    self.conn.execute(
                        "UPDATE files SET status = 'trash', trashed_at = ? WHERE id = ?",
                        (now_ts, fid),
                    )
                    self.conn.commit()
                    logger.info(f"File already missing, marked as trash: id={fid}")
                    return True
                trash_dir = self.get_trash_folder()
                if not trash_dir:
                    root_path = self.get_setting("root_path")
                    if not root_path or not os.path.exists(root_path):
                        root_path = os.getcwd()
                    if config.validate_path(root_path):
                        trash_dir = os.path.join(root_path, config.TRASH_FOLDER_NAME)
                    else:
                        return False
                try:
                    os.makedirs(trash_dir, exist_ok=True)
                except (OSError, IOError) as e:
                    logger.error(f"Failed to create trash directory {trash_dir}: {e}")
                    return False
                fname = os.path.basename(src_path)
                dest_path = os.path.join(trash_dir, fname)
                if os.path.exists(dest_path):
                    base, ext = os.path.splitext(fname)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest_path = os.path.join(trash_dir, f"{base}_{timestamp}{ext}")
                try:
                    shutil.move(src_path, dest_path)
                    logger.info(f"Moved to Trash: {src_path} -> {dest_path}")
                    now_ts = time.time()
                    self.conn.execute(
                        "UPDATE files SET path = ?, status = 'trash', trashed_at = ? WHERE id = ?",
                        (dest_path, now_ts, fid),
                    )
                    self.conn.commit()
                    return True
                except (OSError, IOError, shutil.Error) as e:
                    logger.error(f"Failed to move file to trash {src_path}: {e}")
                    return False
            except sqlite3.Error as e:
                logger.error(f"Database error in move_to_trash for file_id {fid}: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error in move_to_trash for file_id {fid}: {e}", exc_info=True)
                return False

    def get_trash_files(self) -> List[Tuple[int, str, float, str, Optional[float]]]:
        with self.lock:
            try:
                rows = self.conn.execute(
                    "SELECT id, path, mtime, filename, trashed_at FROM files "
                    "WHERE status = 'trash' ORDER BY mtime DESC"
                ).fetchall()
                return [
                    (r[0], r[1], r[2] or 0, r[3] or os.path.basename(r[1]), r[4])
                    for r in rows
                ]
            except sqlite3.Error as e:
                logger.error(f"Failed to get trash files: {e}")
                return []

    def is_permanent_delete_allowed(self, fid: int) -> bool:
        """ゴミ箱行について、退避期間を経過して完全削除してよいか。"""
        if not config.ENFORCE_TRASH_RETENTION_BEFORE_PERMANENT_DELETE:
            return True
        with self.lock:
            row = self.conn.execute(
                "SELECT status, trashed_at FROM files WHERE id = ?", (fid,)
            ).fetchone()
        if not row or row[0] != "trash":
            return False
        trashed_at = row[1]
        if trashed_at is None:
            return True
        elapsed = time.time() - float(trashed_at)
        need = float(config.TRASH_RETENTION_DAYS) * 86400.0
        return elapsed >= need

    def permanent_delete_blocked_reason(self, fid: int) -> Optional[str]:
        """完全削除がブロックされているとき日本語メッセージ、可能なら None。"""
        if not config.ENFORCE_TRASH_RETENTION_BEFORE_PERMANENT_DELETE:
            return None
        with self.lock:
            row = self.conn.execute(
                "SELECT status, trashed_at FROM files WHERE id = ?", (fid,)
            ).fetchone()
        if not row or row[0] != "trash":
            return "ゴミ箱の項目ではありません。"
        trashed_at = row[1]
        if trashed_at is None:
            return None
        elapsed = time.time() - float(trashed_at)
        need = float(config.TRASH_RETENTION_DAYS) * 86400.0
        if elapsed >= need:
            return None
        remain_sec = need - elapsed
        if remain_sec <= 86400:
            hours = max(1, math.ceil(remain_sec / 3600.0))
            tail = f"あとおおよそ {hours} 時間"
        else:
            days = max(1, math.ceil(remain_sec / 86400.0))
            tail = f"あとおおよそ {days} 日"
        return (
            f"安全のため、ゴミ箱に移してから {config.TRASH_RETENTION_DAYS} 日経過するまで完全削除できません。"
            f"（{tail}）"
        )

    def delete_file_record(self, fid: int) -> bool:
        with self.lock:
            try:
                self.conn.execute("DELETE FROM thumbnails WHERE file_id = ?", (fid,))
                self.conn.execute("DELETE FROM files WHERE id = ?", (fid,))
                self.conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"Failed to delete file record id={fid}: {e}")
                return False

    def permanently_delete_file(self, fid: int, force: bool = False) -> bool:
        if not force and not self.is_permanent_delete_allowed(fid):
            logger.warning(f"permanently_delete_file blocked by trash retention: fid={fid}")
            return False
        with self.lock:
            try:
                row = self.conn.execute("SELECT path FROM files WHERE id = ? AND status = 'trash'", (fid,)).fetchone()
                if not row:
                    return False
                path = row[0]
            except sqlite3.Error as e:
                logger.error(f"Database error in permanently_delete_file: {e}")
                return False
        if path and os.path.exists(path) and config.validate_path(path):
            try:
                os.remove(path)
                logger.info(f"Permanently deleted file: {path}")
            except (OSError, IOError) as e:
                logger.error(f"Failed to remove file {path}: {e}")
                return False
        return self.delete_file_record(fid)

    def record_custom_category(self, category_name: str) -> None:
        with self.lock:
            try:
                c = self.conn.cursor()
                c.execute('''INSERT INTO custom_categories (category_name, usage_count, last_used)
                             VALUES (?, 1, CURRENT_TIMESTAMP)
                             ON CONFLICT(category_name) DO UPDATE SET
                             usage_count = usage_count + 1,
                             last_used = CURRENT_TIMESTAMP''', (category_name,))
                self.conn.commit()
                logger.info(f"Database: Recorded custom category '{category_name}'")
            except sqlite3.Error as e:
                logger.error(f"Failed to record custom category: {e}")

    def get_popular_custom_categories(self, limit: int = 10) -> List[Tuple[str, int]]:
        with self.lock:
            try:
                c = self.conn.cursor()
                c.execute('''SELECT category_name, usage_count
                             FROM custom_categories
                             ORDER BY usage_count DESC, last_used DESC
                             LIMIT ?''', (limit,))
                return c.fetchall()
            except sqlite3.Error as e:
                logger.error(f"Failed to get popular custom categories: {e}")
                return []

    def add_custom_category(self, category_name: str) -> bool:
        with self.lock:
            try:
                c = self.conn.cursor()
                c.execute('''INSERT OR IGNORE INTO custom_categories (category_name, usage_count, last_used)
                             VALUES (?, 1, CURRENT_TIMESTAMP)''', (category_name,))
                self.conn.commit()
                return c.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Failed to add custom category: {e}")
                return False

    def remove_custom_category(self, category_name: str) -> bool:
        with self.lock:
            try:
                c = self.conn.cursor()
                c.execute('DELETE FROM custom_categories WHERE category_name = ?', (category_name,))
                self.conn.commit()
                return c.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Failed to remove custom category: {e}")
                return False

    def get_all_custom_categories(self) -> List[str]:
        with self.lock:
            try:
                c = self.conn.cursor()
                c.execute('SELECT category_name FROM custom_categories ORDER BY category_name')
                return [row[0] for row in c.fetchall()]
            except sqlite3.Error as e:
                logger.error(f"Failed to get all custom categories: {e}")
                return []

    def get_file_status(self, fid: int) -> Optional[str]:
        """ファイルIDからステータスを取得。存在しない場合はNone。"""
        with self.lock:
            try:
                row = self.conn.execute("SELECT status FROM files WHERE id = ?", (fid,)).fetchone()
                return row[0] if row else None
            except sqlite3.Error as e:
                logger.error(f"get_file_status error (id={fid}): {e}")
                return None

    def get_file_id_by_path(self, path: str) -> int:
        """パスからファイルIDを取得。存在しない場合は0。"""
        with self.lock:
            try:
                row = self.conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()
                return row[0] if row else 0
            except sqlite3.Error as e:
                logger.error(f"get_file_id_by_path error: {e}")
                return 0

    def get_non_trash_files_raw(self) -> List[Tuple[int, str, int]]:
        """ゴミ箱以外の全ファイル (id, path, size) を取得。"""
        with self.lock:
            try:
                return self.conn.execute(
                    "SELECT id, path, size FROM files WHERE status != 'trash'"
                ).fetchall()
            except sqlite3.Error as e:
                logger.error(f"get_non_trash_files_raw error: {e}")
                return []

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
                logger.info("Database connection closed")
            except sqlite3.Error as e:
                logger.error(f"Error closing database connection: {e}")

import sqlite3
import logging
import os
import shutil
import time
from threading import RLock
from datetime import datetime
from typing import Optional, List, Tuple, Set, Any

from config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    データベース管理クラス
    
    SQLiteデータベースを使用して画像ファイルのメタデータとサムネイルを管理します。
    スレッドセーフな実装です。
    """
    
    def __init__(self, db_path: str = None):
        """
        データベースマネージャーを初期化
        
        Args:
            db_path: データベースファイルのパス（デフォルト: config.DB_NAME）
        """
        self.db_path = db_path or config.DB_NAME
        self.lock = RLock()
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self.init_db()

    def _connect(self) -> None:
        """
        データベース接続を確立
        """
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            if config.DB_WAL_MODE:
                self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database {self.db_path}: {e}")
            raise

    def init_db(self) -> None:
        """
        データベーステーブルとインデックスを初期化
        """
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

                c.execute('CREATE INDEX IF NOT EXISTS idx_path ON files (path)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_status ON files (status)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_hash ON files (hash_value)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_mtime ON files (mtime)')
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to initialize database: {e}")
                raise

    def rebuild_db(self) -> None:
        """
        データベースを完全に再構築（全データ削除）
        
        注意: この操作は不可逆です。すべてのデータが削除されます。
        """
        with self.lock:
            try:
                if self.conn:
                    try:
                        self.conn.close()
                    except sqlite3.Error as e:
                        logger.warning(f"Error closing connection: {e}")
                
                # データベースファイルとWALファイルを削除
                db_files = [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]
                for db_file in db_files:
                    if os.path.exists(db_file):
                        try:
                            os.remove(db_file)
                        except (OSError, IOError) as e:
                            logger.error(f"Failed to remove database file {db_file}: {e}")
                            raise
                
                # 再接続して初期化
                self._connect()
                self.init_db()
                logger.info("Database rebuilt successfully")
            except Exception as e:
                logger.error(f"DB Rebuild Error: {e}", exc_info=True)
                # 再接続を試みる
                try:
                    self._connect()
                except Exception as reconnect_error:
                    logger.error(f"Failed to reconnect after rebuild error: {reconnect_error}")
                    raise

    def set_setting(self, key: str, value: Any) -> None:
        """
        設定値を保存
        
        Args:
            key: 設定キー
            value: 設定値（文字列に変換されます）
        """
        with self.lock:
            try:
                self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                                (key, str(value)))
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to set setting {key}: {e}")
                raise

    def get_setting(self, key: str) -> Optional[str]:
        """
        設定値を取得
        
        Args:
            key: 設定キー
            
        Returns:
            設定値（存在しない場合はNone）
        """
        with self.lock:
            try:
                row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
                return row[0] if row else None
            except sqlite3.Error as e:
                logger.error(f"Failed to get setting {key}: {e}")
                return None
                
    def get_trash_folder(self) -> Optional[str]:
        """
        削除用フォルダのパスを取得
        """
        return self.get_setting("trash_folder")

    def set_trash_folder(self, path: str) -> None:
        """
        削除用フォルダのパスを設定
        """
        self.set_setting("trash_folder", path)

    def save_thumbnail(self, fid: int, data: bytes) -> None:
        """
        サムネイルをデータベースに保存
        
        Args:
            fid: ファイルID
            data: サムネイル画像データ（BLOB）
        """
        with self.lock:
            try:
                self.conn.execute("INSERT OR REPLACE INTO thumbnails (file_id, data) VALUES (?, ?)", 
                                (fid, data))
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to save thumbnail for file_id {fid}: {e}")

    def get_thumbnail(self, fid: int) -> Optional[bytes]:
        """
        サムネイルをデータベースから取得
        
        Args:
            fid: ファイルID
            
        Returns:
            サムネイル画像データ（存在しない場合はNone）
        """
        with self.lock:
            try:
                row = self.conn.execute("SELECT data FROM thumbnails WHERE file_id = ?", (fid,)).fetchone()
                return row[0] if row else None
            except sqlite3.Error as e:
                logger.error(f"Failed to get thumbnail for file_id {fid}: {e}")
                return None

    def insert_file(self, path: str, size: int, mtime: float) -> bool:
        """
        ファイル情報をデータベースに挿入
        
        Args:
            path: ファイルパス
            size: ファイルサイズ（バイト）
            mtime: 更新日時（タイムスタンプ）
            
        Returns:
            挿入成功時True（既に存在する場合はFalse）
        """
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
        """
        複数のファイルをデータベースから削除
        
        Args:
            paths: 削除するファイルパスのセット
        """
        if not paths:
            return
        
        # パス検証
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

    def get_file_count(self) -> int:
        """
        登録されているファイルの総数を取得
        
        Returns:
            ファイル数
        """
        with self.lock:
            try:
                return self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Failed to get file count: {e}")
                return 0

    def get_unprocessed_count(self) -> int:
        """
        未処理ファイルの数を取得
        
        Returns:
            未処理ファイル数
        """
        with self.lock:
            try:
                return self.conn.execute("SELECT COUNT(*) FROM files WHERE status = 'unprocessed'").fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Failed to get unprocessed count: {e}")
                return 0

    def get_unprocessed_files(self, limit: int = 1000) -> List[Tuple[int, str, str, int]]:
        """
        未処理ファイルのリストを取得
        
        Args:
            limit: 取得する最大件数
            
        Returns:
            (id, path, extension, size)のタプルのリスト
        """
        with self.lock:
            try:
                return self.conn.execute(
                    "SELECT id, path, extension, size FROM files WHERE status = 'unprocessed' LIMIT ?", 
                    (limit,)).fetchall()
            except sqlite3.Error as e:
                logger.error(f"Failed to get unprocessed files: {e}")
                return []

    def update_analysis_result(self, fid: int, md5: Optional[str], phash: Optional[str], 
                               blur: float, status: str = 'analyzed') -> None:
        """
        解析結果を更新
        
        Args:
            fid: ファイルID
            md5: MD5ハッシュ値
            phash: パーセプチュアルハッシュ値
            blur: ピンボケスコア
            status: ステータス（デフォルト: 'analyzed'）
        """
        with self.lock:
            try:
                self.conn.execute('UPDATE files SET hash_value=?, p_hash=?, blur_score=?, status=? WHERE id=?',
                                  (md5, phash, blur, status, fid))
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to update analysis result for file_id {fid}: {e}")
                raise

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

    def get_all_files_with_info(self):
        """
        全ファイルのID、パス、タイムスタンプを取得 (EventGrouper用)
        Returns:
            List[Dict]: [{'id': int, 'path': str, 'timestamp': float}, ...]
        """
        with self.lock:
            rows = self.conn.execute("SELECT id, path, mtime FROM files WHERE status != 'trash' ORDER BY mtime ASC").fetchall()
            return [{'id': r[0], 'path': r[1], 'timestamp': r[2]} for r in rows]

    def get_analyzed_files_unsorted(self, limit=100):
        with self.lock: return self.conn.execute("SELECT id, path, p_hash FROM files WHERE status = 'analyzed' LIMIT ?",
                                                 (limit,)).fetchall()
    
    def connect(self):
        """
        raw connection を一時的に取得・作成して返す (backward compatibility用)
        呼び出し元で close を呼ぶ必要があるが、self.conn は共有なので、
        新たに connect するか、self.conn を返すか。
        sorter_ui.py で conn.close() しているので、新しいコネクションを返すべき。
        """
        try:
             conn = sqlite3.connect(self.db_path, check_same_thread=False)
             return conn
        except:
             return None

    def move_file_to_folder(self, fid: int, src: str, folder: str) -> bool:
        """
        ファイルを指定フォルダに移動
        
        Args:
            fid: ファイルID
            src: 移動元パス
            folder: 移動先フォルダ
            
        Returns:
            移動成功時True
        """
        # パス検証
        if not config.validate_path(src) or not config.validate_path(folder):
            logger.warning(f"Invalid path for move_file_to_folder: src={src}, folder={folder}")
            return False
        
        try:
            name = os.path.basename(src)
            dest = os.path.join(folder, name)
            
            # 同じフォルダの場合はスキップ
            if os.path.abspath(os.path.dirname(src)) == os.path.abspath(folder):
                return True
            
            # 同名ファイルが存在する場合はタイムスタンプを追加
            if os.path.exists(dest):
                base, ext = os.path.splitext(name)
                dest = os.path.join(folder, f"{base}_{int(time.time())}{ext}")
            
            shutil.move(src, dest)
            
            with self.lock:
                try:
                    self.conn.execute("UPDATE files SET path = ?, status = 'sorted' WHERE id = ?", (dest, fid))
                    self.conn.commit()
                except sqlite3.Error as db_error:
                    logger.error(f"Failed to update DB after file move: {db_error}")
                    # ファイルは移動済みなのでロールバックは困難
                    return False
            
            return True
        except (OSError, IOError, shutil.Error) as e:
            logger.error(f"Failed to move file {src} to {folder}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error moving file {src} to {folder}: {e}", exc_info=True)
            return False

    def move_to_trash(self, fid: int) -> bool:
        """
        ファイルをゴミ箱フォルダに移動
        
        物理削除ではなく、スキャンルート直下の '_TrashBox' フォルダへ移動します。
        
        Args:
            fid: ファイルID
            
        Returns:
            移動成功時True
        """
        with self.lock:
            try:
                # 1. ファイル情報を取得
                row = self.conn.execute("SELECT path FROM files WHERE id = ?", (fid,)).fetchone()
                if not row:
                    logger.warning(f"File not found in database: id={fid}")
                    return False
                src_path = row[0]

                # パス検証
                if not config.validate_path(src_path):
                    logger.warning(f"Invalid path for move_to_trash: {src_path}")
                    return False

                if not os.path.exists(src_path):
                    # ファイルが既にない場合はDBだけ更新してTrue扱い
                    self.conn.execute("UPDATE files SET status = 'trash' WHERE id = ?", (fid,))
                    self.conn.commit()
                    logger.info(f"File already missing, marked as trash: id={fid}")
                    return True

                # 2. ゴミ箱フォルダの決定
                # 設定テーブルから取得を試みる
                trash_dir = self.get_trash_folder()
                
                if not trash_dir:
                    # 設定なければルートパスの下に作る(旧ロジック)
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

                # 3. 移動先のパス決定 (同名ファイル回避)
                fname = os.path.basename(src_path)
                dest_path = os.path.join(trash_dir, fname)

                if os.path.exists(dest_path):
                    # 同名なら日時をつけてリネーム
                    base, ext = os.path.splitext(fname)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest_path = os.path.join(trash_dir, f"{base}_{timestamp}{ext}")

                # 4. 移動実行
                try:
                    shutil.move(src_path, dest_path)
                    logger.info(f"Moved to Trash: {src_path} -> {dest_path}")

                    # DB更新
                    self.conn.execute("UPDATE files SET path = ?, status = 'trash' WHERE id = ?", (dest_path, fid))
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

    def close(self) -> None:
        """
        データベース接続を閉じる
        """
        if self.conn:
            try:
                self.conn.close()
                logger.info("Database connection closed")
            except sqlite3.Error as e:
                logger.error(f"Error closing database connection: {e}")

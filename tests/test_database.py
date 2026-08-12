"""
データベース機能のユニットテスト
DatabaseManager の主要メソッドを網羅する。
"""
import unittest
import os
import tempfile
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.config import config
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class _DBTestBase(unittest.TestCase):
    """テスト用 DB を一時ディレクトリに作成する共通基盤"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_photos.db")
        self.db = DatabaseManager(self.test_db_path)

    def tearDown(self):
        if self.db:
            self.db.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _make_file(self, name: str, content: str = "test") -> str:
        """一時ファイルを作成してパスを返す"""
        path = os.path.join(self.temp_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _insert(self, name: str = "test.jpg", size: int = 100, mtime: float = 1234567890.0) -> str:
        """ファイルを作成して DB に登録し、パスを返す"""
        path = self._make_file(name)
        self.db.insert_file(path, size, mtime)
        return path

    def _get_id(self, path: str) -> int:
        """パスからファイル ID を取得"""
        with self.db.lock:
            row = self.db.conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()
        return row[0] if row else None


# =================================================================
# 基本操作
# =================================================================
class TestBasicOperations(_DBTestBase):

    def test_database_initialization(self):
        self.assertIsNotNone(self.db.conn)
        self.assertEqual(self.db.get_file_count(), 0)

    def test_insert_and_retrieve_file(self):
        path = self._insert("test.jpg")
        self.assertEqual(self.db.get_file_count(), 1)

    def test_duplicate_insert(self):
        path = self._insert("test.jpg")
        result = self.db.insert_file(path, 100, 1234567890.0)
        self.assertFalse(result)

    def test_error_handling_invalid_path(self):
        result = self.db.insert_file("../../../etc/passwd", 100, 1234567890.0)
        self.assertFalse(result)


# =================================================================
# サムネイル
# =================================================================
class TestThumbnailOperations(_DBTestBase):

    def test_save_and_get_thumbnail(self):
        path = self._insert("thumb.jpg")
        fid = self._get_id(path)
        data = b"fake_thumbnail_blob"
        self.db.save_thumbnail(fid, data)
        self.assertEqual(self.db.get_thumbnail(fid), data)

    def test_get_nonexistent_thumbnail(self):
        self.assertIsNone(self.db.get_thumbnail(9999))


# =================================================================
# 設定
# =================================================================
class TestSettingsOperations(_DBTestBase):

    def test_set_and_get(self):
        self.db.set_setting("key1", "val1")
        self.assertEqual(self.db.get_setting("key1"), "val1")

    def test_overwrite(self):
        self.db.set_setting("key1", "val1")
        self.db.set_setting("key1", "val2")
        self.assertEqual(self.db.get_setting("key1"), "val2")

    def test_nonexistent_key(self):
        self.assertIsNone(self.db.get_setting("no_such_key"))

    def test_trash_folder(self):
        self.db.set_trash_folder("/tmp/trash")
        self.assertEqual(self.db.get_trash_folder(), "/tmp/trash")


# =================================================================
# ファイル削除・取得
# =================================================================
class TestFileRemoval(_DBTestBase):

    def test_remove_files(self):
        p1 = self._insert("a.jpg")
        p2 = self._insert("b.jpg")
        self.assertEqual(self.db.get_file_count(), 2)
        self.db.remove_files({p1, p2})
        self.assertEqual(self.db.get_file_count(), 0)

    def test_remove_empty_set(self):
        self._insert("a.jpg")
        self.db.remove_files(set())
        self.assertEqual(self.db.get_file_count(), 1)

    def test_delete_file_record(self):
        path = self._insert("del.jpg")
        fid = self._get_id(path)
        self.assertTrue(self.db.delete_file_record(fid))
        self.assertEqual(self.db.get_file_count(), 0)


# =================================================================
# prune_missing_file_paths（全パス実在確認）
# =================================================================
class TestPruneMissingPaths(_DBTestBase):

    def test_prune_removes_missing_file(self):
        path = self._insert("gone.jpg")
        self.assertEqual(self.db.get_file_count(), 1)
        os.remove(path)
        n = self.db.prune_missing_file_paths(include_trash=True)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(self.db.get_file_count(), 0)

    def test_prune_keeps_rows_when_parent_folder_is_unreachable(self):
        """OneDrive/NAS が一時的にオフラインのとき、ライブラリ記録を消してはいけない。

        親フォルダごと見えない = ドライブ未接続の可能性が高いので温存する。
        （ファイル単体が消えた場合は従来どおり削除する）
        """
        subdir = os.path.join(self.temp_dir, "offline_drive")
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, "photo.jpg")
        with open(path, "w") as fp:
            fp.write("x")
        self.db.insert_file(path, 100, os.path.getmtime(path))
        self.assertEqual(self.db.get_file_count(), 1)

        # フォルダごと消える = オフライン相当
        shutil.rmtree(subdir)

        n = self.db.prune_missing_file_paths(include_trash=True)
        self.assertEqual(n, 0, "親フォルダが見えないだけで行を消してはいけない")
        self.assertEqual(self.db.get_file_count(), 1)

    def test_prune_keeps_existing(self):
        path = self._insert("stay.jpg")
        n = self.db.prune_missing_file_paths(include_trash=True)
        self.assertEqual(n, 0)
        self.assertEqual(self.db.get_file_count(), 1)
        self.assertIn(path, self.db.get_all_files())

    def test_prune_trash_missing_when_include_trash(self):
        path = self._insert("tr.jpg")
        with self.db.lock:
            self.db.conn.execute("UPDATE files SET status = 'trash' WHERE path = ?", (path,))
            self.db.conn.commit()
        os.remove(path)
        n = self.db.prune_missing_file_paths(include_trash=True)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(self.db.get_file_count(), 0)

    def test_prune_skips_trash_when_disabled(self):
        path = self._insert("tr2.jpg")
        with self.db.lock:
            self.db.conn.execute("UPDATE files SET status = 'trash' WHERE path = ?", (path,))
            self.db.conn.commit()
        os.remove(path)
        n = self.db.prune_missing_file_paths(include_trash=False)
        self.assertEqual(n, 0)
        self.assertEqual(self.db.get_file_count(), 1)


# =================================================================
# get_all_files / get_all_files_with_info
# =================================================================
class TestGetAllFiles(_DBTestBase):

    def test_get_all_files(self):
        p1 = self._insert("f1.jpg")
        p2 = self._insert("f2.jpg")
        paths = self.db.get_all_files()
        self.assertEqual(len(paths), 2)
        self.assertIn(p1, paths)
        self.assertIn(p2, paths)

    def test_get_all_files_with_info(self):
        self._insert("f1.jpg")
        infos = self.db.get_all_files_with_info()
        self.assertEqual(len(infos), 1)
        self.assertIn('id', infos[0])
        self.assertIn('path', infos[0])
        self.assertIn('timestamp', infos[0])

    def test_excludes_trash(self):
        """trash ステータスのファイルは get_all_files に含まれない"""
        path = self._insert("tr.jpg")
        fid = self._get_id(path)
        with self.db.lock:
            self.db.conn.execute("UPDATE files SET status='trash' WHERE id=?", (fid,))
            self.db.conn.commit()
        self.assertEqual(len(self.db.get_all_files()), 0)


# =================================================================
# 解析結果の更新・取得
# =================================================================
class TestAnalysisResults(_DBTestBase):

    def test_update_analysis_result(self):
        path = self._insert("an.jpg")
        fid = self._get_id(path)
        self.db.update_analysis_result(fid, "abc123", "ff00ff", 12.5, 'analyzed')
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT hash_value, p_hash, blur_score, status FROM files WHERE id=?", (fid,)
            ).fetchone()
        self.assertEqual(row[0], "abc123")
        self.assertEqual(row[1], "ff00ff")
        self.assertAlmostEqual(row[2], 12.5)
        self.assertEqual(row[3], "analyzed")

    def test_get_unprocessed_files(self):
        self._insert("u1.jpg")
        self._insert("u2.jpg")
        files = self.db.get_unprocessed_files(limit=10)
        self.assertEqual(len(files), 2)

    def test_get_unprocessed_count(self):
        self._insert("u1.jpg")
        self.assertEqual(self.db.get_unprocessed_count(), 1)

    def test_get_duplicate_hashes(self):
        p1 = self._insert("d1.jpg")
        p2 = self._insert("d2.jpg")
        fid1, fid2 = self._get_id(p1), self._get_id(p2)
        self.db.update_analysis_result(fid1, "samehash", "", 10.0)
        self.db.update_analysis_result(fid2, "samehash", "", 10.0)
        dups = self.db.get_duplicate_hashes()
        self.assertTrue(any(h == "samehash" for h, _size, _cnt in dups))

    def test_get_files_by_hash(self):
        p1 = self._insert("h1.jpg")
        fid1 = self._get_id(p1)
        self.db.update_analysis_result(fid1, "uniquehash", "", 10.0)
        files = self.db.get_files_by_hash("uniquehash")
        self.assertEqual(len(files), 1)

    def test_get_blurry_files(self):
        p = self._insert("blur.jpg")
        fid = self._get_id(p)
        self.db.update_analysis_result(fid, None, "", 5.0, 'analyzed')
        blurry = self.db.get_blurry_files(th=50)
        self.assertTrue(any(fid == r[0] for r in blurry))

    def test_get_files_with_phash(self):
        p = self._insert("ph.jpg")
        fid = self._get_id(p)
        self.db.update_analysis_result(fid, None, "abcdef", 10.0)
        rows = self.db.get_files_with_phash()
        self.assertTrue(any(fid == r[0] for r in rows))


# =================================================================
# 完全ハッシュ
# =================================================================
class TestFullHash(_DBTestBase):

    def _setup_duplicates(self):
        """簡易ハッシュが重複する 2 ファイルを用意"""
        p1 = self._insert("fh1.jpg")
        p2 = self._insert("fh2.jpg")
        fid1, fid2 = self._get_id(p1), self._get_id(p2)
        self.db.update_analysis_result(fid1, "dup_quick", "", 10.0)
        self.db.update_analysis_result(fid2, "dup_quick", "", 10.0)
        return fid1, fid2

    def test_full_hash_column_exists(self):
        """マイグレーションで full_hash カラムが存在する"""
        with self.db.lock:
            cols = [r[1] for r in self.db.conn.execute("PRAGMA table_info(files)").fetchall()]
        self.assertIn("full_hash", cols)

    def test_update_and_query_full_hash(self):
        fid1, fid2 = self._setup_duplicates()
        self.db.update_full_hash(fid1, "aaa111")
        self.db.update_full_hash(fid2, "aaa111")
        dups = self.db.get_duplicate_hashes(use_full_hash=True)
        self.assertTrue(any(h == "aaa111" for h, _size, _cnt in dups))

    def test_full_hash_differentiates(self):
        """完全ハッシュが異なれば重複にならない"""
        fid1, fid2 = self._setup_duplicates()
        self.db.update_full_hash(fid1, "aaa111")
        self.db.update_full_hash(fid2, "bbb222")
        dups = self.db.get_duplicate_hashes(use_full_hash=True)
        self.assertEqual(len(dups), 0)

    def test_get_files_needing_full_hash(self):
        fid1, fid2 = self._setup_duplicates()
        need = self.db.get_files_needing_full_hash(limit=10)
        ids = [r[0] for r in need]
        self.assertIn(fid1, ids)
        self.assertIn(fid2, ids)

    def test_clear_full_hashes(self):
        fid1, fid2 = self._setup_duplicates()
        self.db.update_full_hash(fid1, "xxx")
        self.db.clear_full_hashes()
        need = self.db.get_files_needing_full_hash(limit=10)
        ids = [r[0] for r in need]
        self.assertIn(fid1, ids)

    def test_get_files_by_full_hash(self):
        fid1, fid2 = self._setup_duplicates()
        self.db.update_full_hash(fid1, "same_full")
        self.db.update_full_hash(fid2, "same_full")
        files = self.db.get_files_by_hash("same_full", use_full_hash=True)
        self.assertEqual(len(files), 2)


# =================================================================
# root_path スコープとゴミ箱の関係
# =================================================================
class TestTrashScoping(_DBTestBase):
    """
    ゴミ箱は root_path の外（既定 ~/PhotoSortX_Trash）にあるため、
    root スコープを素通しにしないと Trash ページが常に空になる。
    """

    def setUp(self):
        super().setUp()
        self.lib = os.path.join(self.temp_dir, "library")
        self.trash_dir = os.path.join(self.temp_dir, "PhotoSortX_Trash")
        self._insert("library/keep.jpg")
        self.trashed_path = self._insert("PhotoSortX_Trash/deleted.jpg")
        fid = self._get_id(self.trashed_path)
        with self.db.lock:
            self.db.conn.execute("UPDATE files SET status='trash' WHERE id=?", (fid,))
            self.db.conn.commit()
        self.db.set_setting("root_path", self.lib)

    def test_trash_page_query_returns_trash_outside_root(self):
        page = self.db.get_files_page(page=1, limit=100, include_trash=True, status="trash")
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["path"], self.trashed_path)

    def test_normal_listing_still_scoped_to_root(self):
        page = self.db.get_files_page(page=1, limit=100)
        self.assertEqual(page["total"], 1)
        self.assertTrue(page["items"][0]["path"].endswith("keep.jpg"))

    def test_stats_count_trash_outside_root(self):
        stats = self.db.get_library_stats()
        self.assertEqual(stats["trashed"], 1)

    def test_stats_total_excludes_trash(self):
        stats = self.db.get_library_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["total"], stats["analyzed"] + stats["unprocessed"])

    def test_files_outside_root_still_excluded(self):
        """ゴミ箱以外の root 外ファイルは従来どおり除外される"""
        self._insert("other_library/x.jpg")
        self.assertEqual(self.db.get_files_page(page=1, limit=100)["total"], 1)


# =================================================================
# スマート整理の対象ファイル
# =================================================================
class TestOrganizeSourceScoping(_DBTestBase):
    """スマート整理は実ファイルを移動するので root 外を巻き込んではいけない"""

    def setUp(self):
        super().setUp()
        self.lib = os.path.join(self.temp_dir, "library")
        self._insert("library/a.jpg")
        self._insert("other_library/b.jpg")

    def test_scoped_to_root_by_default(self):
        self.db.set_setting("root_path", self.lib)
        files = self.db.get_all_files_with_info()
        self.assertEqual([os.path.basename(f["path"]) for f in files], ["a.jpg"])

    def test_unscoped_when_requested(self):
        self.db.set_setting("root_path", self.lib)
        self.assertEqual(len(self.db.get_all_files_with_info(scoped_to_root=False)), 2)

    def test_all_files_when_no_root_path(self):
        self.assertEqual(len(self.db.get_all_files_with_info()), 2)

    def test_trash_excluded(self):
        p = self._insert("library/gone.jpg")
        fid = self._get_id(p)
        with self.db.lock:
            self.db.conn.execute("UPDATE files SET status='trash' WHERE id=?", (fid,))
            self.db.conn.commit()
        self.db.set_setting("root_path", self.lib)
        self.assertEqual([os.path.basename(f["path"]) for f in self.db.get_all_files_with_info()], ["a.jpg"])


# =================================================================
# フォルダツリー
# =================================================================
class TestFolderTree(_DBTestBase):
    """移動先フォルダ候補は現在の root_path 配下に限定される"""

    def setUp(self):
        super().setUp()
        self.inside = os.path.join(self.temp_dir, "inside")
        self._insert("inside/a.jpg")
        self._insert("outside/b.jpg")

    def test_scoped_to_root_path_by_default(self):
        self.db.set_setting("root_path", self.inside)
        self.assertEqual(list(self.db.get_folder_tree().keys()), [os.path.normpath(self.inside)])

    def test_unscoped_when_requested(self):
        self.db.set_setting("root_path", self.inside)
        self.assertEqual(len(self.db.get_folder_tree(scoped_to_root=False)), 2)

    def test_all_folders_when_no_root_path(self):
        self.assertEqual(len(self.db.get_folder_tree()), 2)

    def test_counts_files_per_folder(self):
        self._insert("inside/c.jpg")
        self.db.set_setting("root_path", self.inside)
        self.assertEqual(self.db.get_folder_tree()[os.path.normpath(self.inside)], 2)


# =================================================================
# 重複グループ化
# =================================================================
class TestDuplicateGrouping(_DBTestBase):
    """簡易ハッシュ (先頭8KB MD5) 衝突の扱い"""

    def _insert_with_hash(self, name: str, size: int, hash_value: str) -> int:
        path = self._insert(name, size=size)
        fid = self._get_id(path)
        self.db.update_analysis_result(fid, hash_value, "", 10.0)
        return fid

    def test_same_hash_same_size_is_duplicate(self):
        """簡易ハッシュもサイズも同じなら重複グループになる"""
        fid1 = self._insert_with_hash("a.jpg", 2048, "same_head")
        fid2 = self._insert_with_hash("b.jpg", 2048, "same_head")
        groups = self.db.get_duplicate_groups()
        self.assertEqual(len(groups), 1)
        self.assertCountEqual(groups[0][2], [fid1, fid2])

    def test_same_hash_different_size_is_not_duplicate(self):
        """先頭8KBが同じでもサイズが違えば別ファイル扱い（誤検出防止）"""
        self._insert_with_hash("a.mp4", 1_000_000, "same_head")
        self._insert_with_hash("b.mp4", 2_000_000, "same_head")
        self.assertEqual(self.db.get_duplicate_groups(), [])

    def test_get_files_by_hash_filters_by_size(self):
        """size を指定するとサイズ違いは除外される"""
        self._insert_with_hash("a.mp4", 1_000_000, "same_head")
        self._insert_with_hash("b.mp4", 2_000_000, "same_head")
        rows = self.db.get_files_by_hash("same_head", size=1_000_000)
        self.assertEqual(len(rows), 1)

    def test_empty_hash_is_ignored(self):
        """空文字ハッシュ（解析スキップ）は重複候補にしない"""
        self._insert_with_hash("a.mp4", 500, "")
        self._insert_with_hash("b.mp4", 500, "")
        self.assertEqual(self.db.get_duplicate_groups(), [])

    def test_groups_scoped_to_root_path(self):
        """root_path 配下のファイルだけがグループ化される"""
        self._insert_with_hash("inside/a.jpg", 2048, "same_head")
        self._insert_with_hash("outside/b.jpg", 2048, "same_head")
        self.db.set_setting("root_path", os.path.join(self.temp_dir, "inside"))
        self.assertEqual(self.db.get_duplicate_groups(), [])

    def test_full_hash_candidates_respect_size(self):
        """サイズ違いのみの衝突は完全ハッシュ計算の対象にしない"""
        self._insert_with_hash("a.mp4", 1_000_000, "same_head")
        self._insert_with_hash("b.mp4", 2_000_000, "same_head")
        self.assertEqual(self.db.get_files_needing_full_hash(limit=10), [])
        self.assertEqual(self.db.count_files_needing_full_hash(), 0)


# =================================================================
# ゴミ箱
# =================================================================
class TestTrashOperations(_DBTestBase):

    def test_move_to_trash(self):
        path = self._insert("trash_me.jpg")
        fid = self._get_id(path)
        self.db.set_trash_folder(os.path.join(self.temp_dir, "_TrashBox"))
        result = self.db.move_to_trash(fid)
        self.assertTrue(result)
        # 元の場所にファイルがないことを確認
        self.assertFalse(os.path.exists(path))

    def test_move_to_trash_missing_file(self):
        """ファイルが既に存在しない場合、trash ステータスに更新されるだけ"""
        path = self._insert("gone.jpg")
        fid = self._get_id(path)
        os.remove(path)  # 先に消す
        result = self.db.move_to_trash(fid)
        self.assertTrue(result)

    def test_get_trash_files(self):
        path = self._insert("t.jpg")
        fid = self._get_id(path)
        self.db.set_trash_folder(os.path.join(self.temp_dir, "_TrashBox"))
        self.db.move_to_trash(fid)
        trash = self.db.get_trash_files()
        self.assertEqual(len(trash), 1)
        self.assertEqual(len(trash[0]), 5)
        self.assertIsNotNone(trash[0][4])

    def test_permanently_delete_file(self):
        path = self._insert("perm_del.jpg")
        fid = self._get_id(path)
        trash_dir = os.path.join(self.temp_dir, "_TrashBox")
        self.db.set_trash_folder(trash_dir)
        self.db.move_to_trash(fid)
        # 退避期間を通過したことにする
        with self.db.lock:
            self.db.conn.execute(
                "UPDATE files SET trashed_at = ? WHERE id = ?",
                (time.time() - 20 * 86400, fid),
            )
            self.db.conn.commit()
        result = self.db.permanently_delete_file(fid)
        self.assertTrue(result)
        self.assertEqual(self.db.get_file_count(), 0)

    def test_permanent_delete_blocked_within_retention(self):
        path = self._insert("blocked.jpg")
        fid = self._get_id(path)
        self.db.set_trash_folder(os.path.join(self.temp_dir, "_TrashBox"))
        self.db.move_to_trash(fid)
        self.assertFalse(self.db.is_permanent_delete_allowed(fid))
        self.assertIsNotNone(self.db.permanent_delete_blocked_reason(fid))
        self.assertFalse(self.db.permanently_delete_file(fid))
        self.assertEqual(self.db.get_file_count(), 1)

    def test_permanent_delete_legacy_null_trashed_at_allowed(self):
        path = self._insert("legacy.jpg")
        fid = self._get_id(path)
        self.db.set_trash_folder(os.path.join(self.temp_dir, "_TrashBox"))
        self.db.move_to_trash(fid)
        with self.db.lock:
            self.db.conn.execute("UPDATE files SET trashed_at = NULL WHERE id = ?", (fid,))
            self.db.conn.commit()
        self.assertTrue(self.db.is_permanent_delete_allowed(fid))
        self.assertTrue(self.db.permanently_delete_file(fid))
        self.assertEqual(self.db.get_file_count(), 0)


# =================================================================
# カスタムカテゴリ
# =================================================================
class TestCustomCategories(_DBTestBase):

    def test_add_and_get_all(self):
        self.db.add_custom_category("風景")
        self.db.add_custom_category("料理")
        cats = self.db.get_all_custom_categories()
        self.assertIn("風景", cats)
        self.assertIn("料理", cats)

    def test_duplicate_add(self):
        self.assertTrue(self.db.add_custom_category("テスト"))
        self.assertFalse(self.db.add_custom_category("テスト"))  # 重複は False

    def test_remove(self):
        self.db.add_custom_category("削除対象")
        self.assertTrue(self.db.remove_custom_category("削除対象"))
        self.assertNotIn("削除対象", self.db.get_all_custom_categories())

    def test_remove_nonexistent(self):
        self.assertFalse(self.db.remove_custom_category("存在しない"))

    def test_record_and_popular(self):
        self.db.record_custom_category("人気A")
        self.db.record_custom_category("人気A")
        self.db.record_custom_category("人気B")
        popular = self.db.get_popular_custom_categories(limit=5)
        self.assertEqual(popular[0][0], "人気A")
        self.assertEqual(popular[0][1], 2)


# =================================================================
# 再構築
# =================================================================
class TestRebuild(_DBTestBase):

    def test_rebuild_clears_all(self):
        self._insert("rebuild.jpg")
        self.db.set_setting("key", "val")
        self.db.rebuild_db()
        self.assertEqual(self.db.get_file_count(), 0)
        self.assertIsNone(self.db.get_setting("key"))


# =================================================================
# ファイル移動
# =================================================================
class TestMoveFile(_DBTestBase):

    def test_move_file_to_folder(self):
        path = self._insert("move_me.jpg")
        fid = self._get_id(path)
        dest_dir = os.path.join(self.temp_dir, "dest")
        os.makedirs(dest_dir)
        result = self.db.move_file_to_folder(fid, path, dest_dir)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "move_me.jpg")))

    def test_move_same_folder(self):
        """同じフォルダへの移動は何もせず True"""
        path = self._insert("same.jpg")
        fid = self._get_id(path)
        result = self.db.move_file_to_folder(fid, path, self.temp_dir)
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()

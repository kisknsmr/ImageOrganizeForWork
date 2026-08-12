"""
完全ハッシュ計算サービス (src/services/duplicate_service.py) のテスト。
Qt に依存せず API サーバーから実行できることを担保する。
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.services.duplicate_service import file_md5, run_full_hash


class TestFullHashService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = DatabaseManager(os.path.join(self.temp_dir, "test_photos.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _add(self, name: str, content: bytes, quick_hash: str) -> int:
        path = os.path.join(self.temp_dir, name)
        with open(path, 'wb') as fp:
            fp.write(content)
        size = os.path.getsize(path)
        self.db.insert_file(path, size, os.path.getmtime(path))
        with self.db.lock:
            fid = self.db.conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()[0]
        self.db.update_analysis_result(fid, quick_hash, "", 10.0)
        return fid

    def test_file_md5_matches_content(self):
        fid = self._add("a.bin", b"hello world", "q")
        row = self.db.get_file_by_id(fid)
        self.assertEqual(file_md5(row["path"]), "5eb63bbbe01eeed093cb22bb8f5acdc3")

    def test_run_full_hash_distinguishes_same_size_files(self):
        """先頭が同じ・サイズも同じだが中身が違うファイルを完全ハッシュで分離する"""
        head = b"x" * 100
        fid1 = self._add("a.bin", head + b"AAAA", "same_head")
        fid2 = self._add("b.bin", head + b"BBBB", "same_head")
        fid3 = self._add("c.bin", head + b"AAAA", "same_head")

        # 簡易ハッシュでは 3 件が 1 グループ
        self.assertEqual(len(self.db.get_duplicate_groups()[0][2]), 3)

        result = run_full_hash(self.db)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["hashed"], 3)
        self.assertEqual(result["failed"], 0)

        groups = self.db.get_duplicate_groups(use_full_hash=True)
        self.assertEqual(len(groups), 1)
        self.assertCountEqual(groups[0][2], [fid1, fid3])
        self.assertNotIn(fid2, groups[0][2])

    def test_run_full_hash_reports_progress(self):
        self._add("a.bin", b"x" * 10, "q")
        self._add("b.bin", b"y" * 10, "q")
        seen = []
        run_full_hash(self.db, progress_cb=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen[-1], (2, 2))

    def test_run_full_hash_with_no_candidates(self):
        self._add("only.bin", b"solo", "unique")
        result = run_full_hash(self.db)
        self.assertEqual(result["total"], 0)

    def test_missing_file_counted_as_failure(self):
        fid = self._add("gone.bin", b"x" * 10, "q")
        self._add("stay.bin", b"y" * 10, "q")
        row = self.db.get_file_by_id(fid)
        os.remove(row["path"])
        result = run_full_hash(self.db)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["hashed"], 1)


if __name__ == '__main__':
    unittest.main()

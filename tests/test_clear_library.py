"""
読み込み記録の消去（clear_scan_records）のテスト。

守るべき性質:
  - ディスク上のファイルは消さない
  - ゴミ箱の記録は消さない（消すと元の場所へ戻せなくなる）
  - サムネイルも一緒に消える（記録だけ残ると孤児になる）
  - root_path を指定したときは、その配下だけが対象
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager


class TestClearScanRecords(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = DatabaseManager(os.path.join(self.temp_dir, "test.db"))
        self.lib_a = os.path.join(self.temp_dir, "libA")
        self.lib_b = os.path.join(self.temp_dir, "libB")
        os.makedirs(self.lib_a)
        os.makedirs(self.lib_b)
        # ゴミ箱も一時ディレクトリに向ける。既定のままだと
        # リポジトリ直下に _TrashBox が作られてテスト実行が作業ツリーを汚す
        self.db.set_trash_folder(os.path.join(self.temp_dir, "trash"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _add(self, folder: str, name: str) -> tuple[str, int]:
        path = os.path.join(folder, name)
        with open(path, "w") as fp:
            fp.write("x")
        self.db.insert_file(path, 1, 1234567890.0)
        with self.db.lock:
            fid = self.db.conn.execute(
                "SELECT id FROM files WHERE path = ?", (path,)
            ).fetchone()[0]
        return path, fid

    def test_clears_current_root_only(self):
        path_a, _ = self._add(self.lib_a, "a.jpg")
        self._add(self.lib_b, "b.jpg")

        result = self.db.clear_scan_records(self.lib_a)

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(self.db.get_file_count(), 1, "別ライブラリの記録まで消えている")
        self.assertTrue(os.path.exists(path_a), "ディスク上のファイルを消してはいけない")

    def test_clears_all_when_root_is_none(self):
        self._add(self.lib_a, "a.jpg")
        self._add(self.lib_b, "b.jpg")

        result = self.db.clear_scan_records(None)

        self.assertEqual(result["deleted"], 2)
        self.assertEqual(self.db.get_file_count(), 0)

    def test_keeps_trash_records(self):
        _, fid = self._add(self.lib_a, "trashed.jpg")
        self.db.move_to_trash(fid)
        self._add(self.lib_a, "normal.jpg")

        result = self.db.clear_scan_records(None)

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["kept_trash"], 1)
        with self.db.lock:
            remaining = self.db.conn.execute(
                "SELECT status FROM files").fetchall()
        self.assertEqual([r[0] for r in remaining], ["trash"])

    def test_removes_thumbnails(self):
        _, fid = self._add(self.lib_a, "a.jpg")
        self.db.save_thumbnail(fid, b"\xff\xd8thumb")
        self.assertIsNotNone(self.db.get_thumbnail(fid))

        self.db.clear_scan_records(None)

        with self.db.lock:
            count = self.db.conn.execute(
                "SELECT COUNT(*) FROM thumbnails").fetchone()[0]
        self.assertEqual(count, 0, "サムネイルが孤児として残っている")

    def test_empty_library_is_noop(self):
        result = self.db.clear_scan_records(None)
        self.assertEqual(result, {"deleted": 0, "kept_trash": 0})


if __name__ == '__main__':
    unittest.main()

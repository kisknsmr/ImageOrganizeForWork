"""
run_scan / run_analyze のユニットテスト（PyQt 非依存）
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.services.scan_analyze_service import run_analyze, run_scan


class TestRunScan(unittest.TestCase):
    """差分スキャン（run_scan）の挙動テスト"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = DatabaseManager(self.db_path)
        self.scan_dir = os.path.join(self.temp_dir, "photos")
        os.makedirs(self.scan_dir, exist_ok=True)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def _create_image(self, name: str) -> str:
        path = os.path.join(self.scan_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"\xFF\xD8\xFF" + b"\x00" * 100)
        return path

    def _run_scanner(self):
        run_scan(self.db, self.scan_dir)

    def test_empty_folder_scan(self):
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 0)

    def test_new_files_registered(self):
        self._create_image("a.jpg")
        self._create_image("sub/b.png")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 2)

    def test_no_double_insert(self):
        self._create_image("a.jpg")
        self._run_scanner()
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 1)

    def test_incremental_scan(self):
        self._create_image("a.jpg")
        self._run_scanner()
        self._create_image("b.jpg")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 2)

    def test_missing_file_removed(self):
        path = self._create_image("gone.jpg")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 1)

        os.remove(path)
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 0)

    def test_other_root_files_preserved(self):
        other_dir = os.path.join(self.temp_dir, "other_photos")
        os.makedirs(other_dir)
        other_file = os.path.join(other_dir, "keep.jpg")
        with open(other_file, "wb") as f:
            f.write(b"\xFF\xD8\xFF" + b"\x00" * 50)
        self.db.insert_file(other_file, 53, 1234567890.0)
        self.assertEqual(self.db.get_file_count(), 1)

        self._run_scanner()
        all_files = self.db.get_all_files()
        self.assertIn(other_file, [os.path.normpath(p) for p in all_files])

    def test_non_image_files_ignored(self):
        txt_path = os.path.join(self.scan_dir, "readme.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("hello")
        self._create_image("a.jpg")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 1)

    def test_stop_flag(self):
        for i in range(50):
            self._create_image(f"img_{i:03d}.jpg")
        result = run_scan(self.db, self.scan_dir, should_stop=lambda: True)
        self.assertTrue(result.get("stopped"))
        self.assertLessEqual(self.db.get_file_count(), 50)

    def test_root_path_saved(self):
        self._run_scanner()
        saved = self.db.get_setting("root_path")
        self.assertEqual(saved, self.scan_dir)


class TestRunAnalyze(unittest.TestCase):
    """run_analyze の基本テスト"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_no_files(self):
        run_analyze(self.db)
        self.assertEqual(self.db.get_unprocessed_count(), 0)

    def test_stop_flag(self):
        run_analyze(self.db, should_stop=lambda: True)


if __name__ == "__main__":
    unittest.main()

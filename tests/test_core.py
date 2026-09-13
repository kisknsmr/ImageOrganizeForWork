"""
コア機能のユニットテスト
"""
import unittest
import os
import tempfile
import shutil
import sys

# テスト用のパスを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import format_eta, hamming_dist, format_file_size, format_file_size_kb
from src.config import config
from src.database import DatabaseManager


class TestUtilFunctions(unittest.TestCase):
    """cv2 / PyQt 不要の軽量関数テスト"""

    def test_format_eta(self):
        """ETAフォーマットのテスト"""
        self.assertEqual(format_eta(0), "00:00")
        self.assertEqual(format_eta(30), "00:30")
        self.assertEqual(format_eta(90), "01:30")
        self.assertEqual(format_eta(3661), "01:01:01")
        self.assertEqual(format_eta(-1), "--:--")

    def test_hamming_dist(self):
        """ハミング距離のテスト"""
        self.assertEqual(hamming_dist(0, 0), 0)
        self.assertEqual(hamming_dist(1, 0), 1)
        self.assertEqual(hamming_dist(0b1010, 0b1100), 2)

    def test_format_file_size(self):
        """ファイルサイズフォーマットのテスト"""
        self.assertEqual(format_file_size(0), "0.0 B")
        self.assertEqual(format_file_size(1024), "1.0 KB")
        self.assertEqual(format_file_size(1048576), "1.0 MB")
        self.assertEqual(format_file_size(-1), "不明")

    def test_format_file_size_kb(self):
        """ファイルサイズKB表示のテスト"""
        self.assertEqual(format_file_size_kb(0), "0 KB")
        self.assertEqual(format_file_size_kb(1024), "1 KB")
        self.assertEqual(format_file_size_kb(1536), "1 KB")
        self.assertEqual(format_file_size_kb(-1), "不明")


class TestDatabaseManager(unittest.TestCase):
    """データベースマネージャーのテスト"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_photos.db")
        self.db = DatabaseManager(self.test_db_path)

    def tearDown(self):
        if self.db:
            self.db.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_insert_file(self):
        """ファイル挿入のテスト"""
        test_path = os.path.join(self.temp_dir, "test.jpg")
        with open(test_path, 'w') as f:
            f.write("test")

        result = self.db.insert_file(test_path, 100, 1234567890.0)
        self.assertTrue(result)

        result = self.db.insert_file(test_path, 100, 1234567890.0)
        self.assertFalse(result)

    def test_get_file_count(self):
        """ファイル数の取得テスト"""
        self.assertEqual(self.db.get_file_count(), 0)

        test_path = os.path.join(self.temp_dir, "test.jpg")
        with open(test_path, 'w') as f:
            f.write("test")

        self.db.insert_file(test_path, 100, 1234567890.0)
        self.assertEqual(self.db.get_file_count(), 1)

    def test_get_unprocessed_count(self):
        """未処理ファイル数の取得テスト"""
        self.assertEqual(self.db.get_unprocessed_count(), 0)

    def test_settings(self):
        """設定の保存・取得テスト"""
        self.db.set_setting("test_key", "test_value")
        value = self.db.get_setting("test_key")
        self.assertEqual(value, "test_value")

        value = self.db.get_setting("nonexistent_key")
        self.assertIsNone(value)


class TestPathValidation(unittest.TestCase):
    """パス検証のテスト"""

    def test_validate_path_normal(self):
        self.assertTrue(config.validate_path("C:\\Users\\test\\image.jpg"))
        self.assertTrue(config.validate_path("/home/user/image.jpg"))
        self.assertTrue(config.validate_path("image.jpg"))

    def test_validate_path_traversal(self):
        self.assertFalse(config.validate_path("../../../etc/passwd"))
        self.assertFalse(config.validate_path("..\\..\\..\\windows\\system32"))
        self.assertFalse(config.validate_path("../test"))

    def test_validate_path_too_long(self):
        long_path = "a" * (config.MAX_PATH_LENGTH + 1)
        self.assertFalse(config.validate_path(long_path))

    def test_validate_path_empty(self):
        self.assertFalse(config.validate_path(""))
        self.assertFalse(config.validate_path(None))


if __name__ == '__main__':
    unittest.main()

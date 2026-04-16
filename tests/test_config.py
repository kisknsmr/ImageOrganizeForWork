"""
設定管理のユニットテスト
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config


class TestConfig(unittest.TestCase):
    """設定のテスト"""
    
    def test_default_values(self):
        """デフォルト値のテスト"""
        self.assertIsNotNone(config.DB_NAME)
        self.assertIsNotNone(config.DEFAULT_WINDOW_SIZE)
        self.assertIsNotNone(config.IMAGE_EXTENSIONS)
        self.assertIsNotNone(config.VIDEO_EXTENSIONS)
    
    def test_all_extensions(self):
        """全拡張子のテスト"""
        all_exts = config.ALL_EXTENSIONS
        self.assertIn('.jpg', all_exts)
        self.assertIn('.mp4', all_exts)
        self.assertNotIn('.txt', all_exts)
    
    def test_validate_path_normal(self):
        """正常なパスの検証テスト"""
        self.assertTrue(config.validate_path("C:\\Users\\test\\image.jpg"))
        self.assertTrue(config.validate_path("/home/user/image.jpg"))
        self.assertTrue(config.validate_path("image.jpg"))
    
    def test_validate_path_traversal(self):
        """パストラバーサル攻撃の検証テスト"""
        self.assertFalse(config.validate_path("../../../etc/passwd"))
        self.assertFalse(config.validate_path("..\\..\\..\\windows\\system32"))
        self.assertFalse(config.validate_path("../test"))
    
    def test_validate_path_too_long(self):
        """長すぎるパスの検証テスト"""
        long_path = "a" * (config.MAX_PATH_LENGTH + 1)
        self.assertFalse(config.validate_path(long_path))
    
    def test_validate_path_empty(self):
        """空のパスの検証テスト"""
        self.assertFalse(config.validate_path(""))
        self.assertFalse(config.validate_path(None))
    
    def test_get_default_trash_folder(self):
        """デフォルト削除フォルダの取得テスト"""
        trash_folder = config.get_default_trash_folder()
        self.assertIsNotNone(trash_folder)
        self.assertIsInstance(trash_folder, str)
        self.assertGreater(len(trash_folder), 0)


if __name__ == '__main__':
    unittest.main()

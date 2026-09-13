"""
差分スキャン（ScannerThread）の「削除対象パス」判定ロジックのテスト。

path_under_root の挙動を検証し、以下を保証する:
- 同じフォルダをスキャンしたとき: ディスクから消えたファイルのみ DB 削除対象になる
- 全く新しいフォルダを開いたとき: 旧フォルダの DB レコードは削除対象に含まれない（誤削除防止）
- D:\\Photos と D:\\Photos2 のようにプレフィックスが同じ別フォルダは含めない
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import path_under_root as path_under_root_to_test


class TestPathUnderRoot(unittest.TestCase):
    """path_under_root の挙動: 削除対象に含めるべきパスのみ True"""

    def test_under_same_root(self):
        """同じルート直下のファイルは True"""
        root = "D:\\Photos" if os.name == "nt" else "/photos"
        path = os.path.join(root, "a.jpg")
        self.assertTrue(path_under_root_to_test(path, root))

    def test_under_subdir(self):
        """ルートのサブディレクトリのファイルは True"""
        root = "D:\\Photos" if os.name == "nt" else "/photos"
        path = os.path.join(root, "2024", "01", "a.jpg")
        self.assertTrue(path_under_root_to_test(path, root))

    def test_sibling_folder_not_under(self):
        """同名プレフィックスの別フォルダ（Photos2）は False → 誤削除しない"""
        root = "D:\\Photos" if os.name == "nt" else "/photos"
        path = "D:\\Photos2\\a.jpg" if os.name == "nt" else "/photos2/a.jpg"
        self.assertFalse(path_under_root_to_test(path, root))

    def test_different_root_not_under(self):
        """全く別のルートのパスは False（新規フォルダを開いたときに旧 DB が消えない）"""
        new_root = "E:\\NewFolder" if os.name == "nt" else "/new_folder"
        old_path = "D:\\OldFolder\\a.jpg" if os.name == "nt" else "/old_folder/a.jpg"
        self.assertFalse(path_under_root_to_test(old_path, new_root))

    def test_root_itself(self):
        """ルート自身のパスは True（ルートがファイルとして登録されることは稀だが）"""
        root = "D:\\Photos" if os.name == "nt" else "/photos"
        self.assertTrue(path_under_root_to_test(root, root))

    def test_trailing_slash_normalized(self):
        """末尾スラッシュは normpath で吸収される"""
        root = "D:\\Photos" if os.name == "nt" else "/photos"
        path = os.path.join(root, "a.jpg")
        root_trailing = root + os.sep
        self.assertTrue(path_under_root_to_test(path, root_trailing))


if __name__ == "__main__":
    unittest.main()

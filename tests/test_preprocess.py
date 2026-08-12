"""
preprocess_service（フォルダ前処理: 画像/動画/その他への振り分け）のユニットテスト。
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.preprocess_service import (
    MOVIES_DIR,
    OTHERS_DIR,
    PICTURES_DIR,
    run_preprocess,
)


class TestRunPreprocess(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _touch(self, rel_path: str) -> str:
        full = os.path.join(self.temp_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fp:
            fp.write(b"x")
        return full

    def test_sorts_by_category_preserving_structure(self):
        self._touch("Event1/photo.jpg")
        self._touch("Event1/clip.mp4")
        self._touch("Event1/notes.txt")
        self._touch("top.png")

        result = run_preprocess(self.temp_dir)

        self.assertEqual(result["total"], 4)
        self.assertEqual(result["moved"], 4)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["pictures"], 2)  # Event1/photo.jpg, top.png
        self.assertEqual(result["movies"], 1)  # Event1/clip.mp4
        self.assertEqual(result["others"], 1)  # Event1/notes.txt
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, PICTURES_DIR, "Event1", "photo.jpg")))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, MOVIES_DIR, "Event1", "clip.mp4")))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, OTHERS_DIR, "Event1", "notes.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, PICTURES_DIR, "top.png")))
        # 元のファイルは移動済みでもう存在しない
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "Event1", "photo.jpg")))

    def test_no_files_returns_zero(self):
        result = run_preprocess(self.temp_dir)
        self.assertEqual(
            result,
            {"stopped": False, "moved": 0, "skipped": 0, "total": 0, "pictures": 0, "movies": 0, "others": 0},
        )

    def test_rerun_is_idempotent(self):
        self._touch("a.jpg")
        first = run_preprocess(self.temp_dir)
        self.assertEqual(first["moved"], 1)

        second = run_preprocess(self.temp_dir)
        # 既にカテゴリフォルダの中にあるファイルは対象外
        self.assertEqual(second["total"], 0)

    def test_existing_destination_is_skipped_not_overwritten(self):
        self._touch("a.jpg")
        dest_dir = os.path.join(self.temp_dir, PICTURES_DIR)
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, "a.jpg"), "wb") as fp:
            fp.write(b"existing")

        result = run_preprocess(self.temp_dir)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["moved"], 0)
        # 元のファイルは上書き衝突を避けるためそのまま残る
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "a.jpg")))

    def test_trash_folder_excluded(self):
        from src.config import config

        self._touch(f"{config.TRASH_FOLDER_NAME}/old.jpg")
        result = run_preprocess(self.temp_dir)
        self.assertEqual(result["total"], 0)

    def test_stop_flag_halts_early(self):
        self._touch("a.jpg")
        self._touch("b.jpg")
        result = run_preprocess(self.temp_dir, should_stop=lambda: True)
        self.assertTrue(result["stopped"])


if __name__ == "__main__":
    unittest.main()

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
    count_targets,
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

    def test_count_targets_matches_run_result(self):
        """
        事前カウントと実行結果が一致すること。

        画面の「見つかった件数」と「対象N件中」がずれて見えていた原因は、
        事前カウントが別基準（対応拡張子のみ・カテゴリフォルダの中も含む）
        だったこと。両者が同じ対象定義を使うことを保証する。
        """
        self._touch("loose/a.jpg")
        self._touch("loose/b.png")
        self._touch("loose/deep/c.tiff")
        self._touch("loose/notes.txt")   # 未対応拡張子 → Others
        self._touch("top.mp4")
        # 既に振り分け済みのものは対象外
        self._touch(f"{PICTURES_DIR}/done1.jpg")
        self._touch(f"{PICTURES_DIR}/sub/done2.jpg")
        self._touch(f"{MOVIES_DIR}/done.mp4")

        preview = count_targets(self.temp_dir)
        result = run_preprocess(self.temp_dir)

        self.assertEqual(preview["total"], result["total"])
        self.assertEqual(preview["pictures"], result["pictures"])
        self.assertEqual(preview["movies"], result["movies"])
        self.assertEqual(preview["others"], result["others"])
        self.assertEqual(preview["total"], 5)
        self.assertEqual(preview["pictures"], 3)
        self.assertEqual(preview["movies"], 1)
        self.assertEqual(preview["others"], 1)

    def test_count_targets_is_zero_after_sorting(self):
        """振り分け後に再度数えると 0 になること（再実行しても対象が残らない）"""
        self._touch("loose/a.jpg")
        run_preprocess(self.temp_dir)
        self.assertEqual(count_targets(self.temp_dir)["total"], 0)

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

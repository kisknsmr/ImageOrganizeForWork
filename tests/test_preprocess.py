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
    remove_empty_dirs,
    summarize_empty_dirs,
    summarize_folder,
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

        # 内訳の整合はカテゴリ内も数えるフルモードで検証する
        preview = summarize_folder(self.temp_dir, full=True)
        result = run_preprocess(self.temp_dir, full=True)

        for key in ("all_files", "total", "already_sorted", "pictures", "movies", "others"):
            self.assertEqual(preview[key], result[key], f"{key} が事前カウントと結果で食い違う")

        # 全ファイル = 振り分け対象 + 対応不要 が成り立つこと
        self.assertEqual(preview["all_files"], preview["total"] + preview["already_sorted"])
        self.assertEqual(preview["all_files"], 8)
        self.assertEqual(preview["total"], 5)
        self.assertEqual(preview["already_sorted"], 3)
        self.assertEqual(preview["pictures"], 3)
        self.assertEqual(preview["movies"], 1)
        self.assertEqual(preview["others"], 1)

    def test_count_targets_is_zero_after_sorting(self):
        """振り分け後に再度数えると 0 になること（再実行しても対象が残らない）"""
        self._touch("loose/a.jpg")
        run_preprocess(self.temp_dir)
        after = summarize_folder(self.temp_dir, full=True)
        self.assertEqual(after["total"], 0)
        # 消えたわけではなく「対応不要」に移っただけ
        self.assertEqual(after["all_files"], 1)
        self.assertEqual(after["already_sorted"], 1)

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
            {"stopped": False, "moved": 0, "skipped": 0, "total": 0,
             "all_files": 0, "already_sorted": 0,
             "unsorted": 0, "misplaced": 0, "rechecked": 0, "full": False,
             "pictures": 0, "movies": 0, "others": 0},
        )

    def test_incremental_ignores_category_folders(self):
        """差分モードでは振り分け済みのファイルを一切見ない"""
        self._touch(f"{OTHERS_DIR}/legacy.heic")   # 今の基準では画像
        self._touch("loose/new.jpg")

        preview = summarize_folder(self.temp_dir, full=False)
        self.assertEqual(preview["total"], 1)
        self.assertEqual(preview["unsorted"], 1)
        self.assertEqual(preview["misplaced"], 0)
        # カテゴリフォルダの中は走査しないので母数にも入らない
        self.assertEqual(preview["all_files"], 1)

        result = run_preprocess(self.temp_dir, full=False)
        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["rechecked"], 0)
        # 03 Others のままで動かされていない
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, OTHERS_DIR, "legacy.heic")))

    def test_full_moves_misclassified_file(self):
        """
        フルモードは分類を見直す。

        対応拡張子が増える前に 03 Others へ落ちた画像を、
        今の基準で 01 Pictures へ移し直せること。
        """
        self._touch(f"{OTHERS_DIR}/Event1/legacy.heic")
        self._touch(f"{PICTURES_DIR}/ok.jpg")

        preview = summarize_folder(self.temp_dir, full=True)
        self.assertEqual(preview["all_files"], 2)
        self.assertEqual(preview["misplaced"], 1)
        self.assertEqual(preview["unsorted"], 0)
        self.assertEqual(preview["already_sorted"], 1)

        result = run_preprocess(self.temp_dir, full=True)
        self.assertEqual(result["rechecked"], 1)
        self.assertEqual(result["moved"], 1)
        # カテゴリ名を除いた階層が移動先で保たれる
        self.assertTrue(
            os.path.exists(os.path.join(self.temp_dir, PICTURES_DIR, "Event1", "legacy.heic")))
        self.assertFalse(
            os.path.exists(os.path.join(self.temp_dir, OTHERS_DIR, "Event1", "legacy.heic")))
        # 正しい場所にあったファイルは触らない
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, PICTURES_DIR, "ok.jpg")))

    def test_full_is_idempotent(self):
        """フルモードを繰り返しても、2 回目は移動対象が無いこと"""
        self._touch(f"{OTHERS_DIR}/legacy.heic")
        run_preprocess(self.temp_dir, full=True)
        second = summarize_folder(self.temp_dir, full=True)
        self.assertEqual(second["total"], 0)
        self.assertEqual(second["misplaced"], 0)
        self.assertEqual(second["already_sorted"], 1)

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
        # ゴミ箱の中身は「全ファイル」にも「対応不要」にも数えない
        self.assertEqual(result["all_files"], 0)
        self.assertEqual(result["already_sorted"], 0)

    def test_stop_flag_halts_early(self):
        self._touch("a.jpg")
        self._touch("b.jpg")
        result = run_preprocess(self.temp_dir, should_stop=lambda: True)
        self.assertTrue(result["stopped"])


class TestRemoveEmptyDirs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _mkdir(self, rel_path: str) -> str:
        full = os.path.join(self.temp_dir, rel_path)
        os.makedirs(full, exist_ok=True)
        return full

    def _touch(self, rel_path: str) -> str:
        full = os.path.join(self.temp_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fp:
            fp.write(b"x")
        return full

    def _exists(self, rel_path: str) -> bool:
        return os.path.exists(os.path.join(self.temp_dir, rel_path))

    def test_removes_chain_of_empty_dirs_at_any_depth(self):
        """空フォルダが何階層連なっていても、1 回でまとめて消えること"""
        self._mkdir(os.path.join("a", "b", "c", "d", "e"))

        preview = summarize_empty_dirs(self.temp_dir)
        result = remove_empty_dirs(self.temp_dir)

        self.assertEqual(preview["total"], 5)
        self.assertEqual(preview["max_depth"], 5)
        self.assertEqual(result["removed"], 5)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["max_depth"], 5)
        self.assertFalse(self._exists("a"))
        # root 自身は消さない
        self.assertTrue(os.path.isdir(self.temp_dir))

    def test_keeps_dirs_that_still_hold_files(self):
        """ファイルが残っている階層から上は残り、その下の空だけが消えること"""
        self._touch(os.path.join("a", "keep.jpg"))
        self._mkdir(os.path.join("a", "empty", "deeper"))

        result = remove_empty_dirs(self.temp_dir)

        self.assertEqual(result["removed"], 2)
        self.assertTrue(self._exists(os.path.join("a", "keep.jpg")))
        self.assertFalse(self._exists(os.path.join("a", "empty")))

    def test_dir_with_only_junk_files_is_treated_as_empty(self):
        """Thumbs.db しか無いフォルダは、エクスプローラー上は空なので残骸ごと消す"""
        self._touch(os.path.join("a", "b", "Thumbs.db"))

        result = remove_empty_dirs(self.temp_dir)

        self.assertEqual(result["removed"], 2)
        self.assertEqual(result["junk_removed"], 1)
        self.assertFalse(self._exists("a"))

    def test_trash_and_category_dirs_are_kept(self):
        """ゴミ箱と直下の 01/02/03 は空でも受け皿として残すこと"""
        from src.config import config

        self._mkdir(config.TRASH_FOLDER_NAME)
        self._mkdir(os.path.join(config.TRASH_FOLDER_NAME, "old"))
        self._mkdir(PICTURES_DIR)
        self._mkdir(MOVIES_DIR)
        self._mkdir(os.path.join(OTHERS_DIR, "sub"))

        result = remove_empty_dirs(self.temp_dir)

        # 消えるのは 03 Others/sub だけ（カテゴリ「直下」だけが保護対象）
        self.assertEqual(result["removed"], 1)
        self.assertTrue(self._exists(config.TRASH_FOLDER_NAME))
        self.assertTrue(self._exists(os.path.join(config.TRASH_FOLDER_NAME, "old")))
        self.assertTrue(self._exists(PICTURES_DIR))
        self.assertTrue(self._exists(MOVIES_DIR))
        self.assertTrue(self._exists(OTHERS_DIR))
        self.assertFalse(self._exists(os.path.join(OTHERS_DIR, "sub")))

    def test_after_preprocess_source_dirs_can_be_cleaned(self):
        """振り分けで空になった元フォルダを、続けて片付けられること"""
        self._touch(os.path.join("Event1", "day1", "photo.jpg"))
        run_preprocess(self.temp_dir)
        self.assertTrue(self._exists(os.path.join("Event1", "day1")))

        result = remove_empty_dirs(self.temp_dir)

        self.assertEqual(result["removed"], 2)  # Event1/day1 と Event1
        self.assertFalse(self._exists("Event1"))
        # 移動先はファイルがあるので当然残る
        self.assertTrue(
            self._exists(os.path.join(PICTURES_DIR, "Event1", "day1", "photo.jpg")))

    def test_no_empty_dirs_returns_zero(self):
        self._touch("a.jpg")
        result = remove_empty_dirs(self.temp_dir)
        self.assertEqual(
            result,
            {"stopped": False, "removed": 0, "failed": 0,
             "total": 0, "max_depth": 0, "junk_removed": 0},
        )

    def test_stop_flag_halts_early(self):
        self._mkdir(os.path.join("a", "b"))
        result = remove_empty_dirs(self.temp_dir, should_stop=lambda: True)
        self.assertTrue(result["stopped"])
        self.assertEqual(result["removed"], 0)
        self.assertTrue(self._exists(os.path.join("a", "b")))


if __name__ == "__main__":
    unittest.main()

"""
organize_service（スマート整理サービス）のユニットテスト。
時間ベースのイベントグルーピングと、グループ単位のフォルダ移動を検証する。
"""
import unittest
import os
import shutil
import sys
import tempfile
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.services import organize_service

logging.basicConfig(level=logging.WARNING)

HOUR = 3600.0
BASE_TS = 1700000000.0  # 2023-11-15 頃


class _OrganizeTestBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_photos.db")
        self.db = DatabaseManager(self.test_db_path)

    def tearDown(self):
        if self.db:
            self.db.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _insert(self, name: str, mtime: float) -> int:
        path = os.path.join(self.temp_dir, name)
        with open(path, "w") as fp:
            fp.write("x")
        self.db.insert_file(path, 100, mtime)
        return self.db.get_file_id_by_path(path)


class TestSanitizeFolderName(unittest.TestCase):
    def test_invalid_chars_replaced(self):
        self.assertEqual(organize_service.sanitize_folder_name('a<b>:c"|?*'), "a_b__c____")

    def test_path_separators_replaced(self):
        self.assertNotIn("\\", organize_service.sanitize_folder_name("a\\b/c"))
        self.assertNotIn("/", organize_service.sanitize_folder_name("a\\b/c"))

    def test_empty_becomes_default(self):
        self.assertEqual(organize_service.sanitize_folder_name("   "), "無題")
        self.assertEqual(organize_service.sanitize_folder_name("..."), "無題")

    def test_normal_name_kept(self):
        self.assertEqual(organize_service.sanitize_folder_name("2024-01-01 旅行"), "2024-01-01 旅行")


class TestCapabilities(unittest.TestCase):
    def test_keys_and_time_mode(self):
        caps = organize_service.capabilities()
        self.assertTrue(caps["time"])
        for key in ("content", "hybrid", "ai_dependencies_installed"):
            self.assertIn(key, caps)


class TestBuildTimeGroups(_OrganizeTestBase):
    def test_gap_splits_groups(self):
        """6時間を超える間隔でイベントが分割される"""
        self._insert("a.jpg", BASE_TS)
        self._insert("b.jpg", BASE_TS + HOUR)
        self._insert("c.jpg", BASE_TS + 24 * HOUR)
        groups = organize_service.build_time_groups(self.db, gap_hours=6.0)
        self.assertEqual(len(groups), 2)
        counts = sorted(g["count"] for g in groups)
        self.assertEqual(counts, [1, 2])

    def test_single_group_when_gap_large(self):
        self._insert("a.jpg", BASE_TS)
        self._insert("b.jpg", BASE_TS + 24 * HOUR)
        groups = organize_service.build_time_groups(self.db, gap_hours=48.0)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 2)

    def test_min_group_size_filters(self):
        self._insert("a.jpg", BASE_TS)
        self._insert("b.jpg", BASE_TS + HOUR)
        self._insert("c.jpg", BASE_TS + 24 * HOUR)
        groups = organize_service.build_time_groups(self.db, gap_hours=6.0, min_group_size=2)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 2)

    def test_payload_shape(self):
        fid = self._insert("a.jpg", BASE_TS)
        groups = organize_service.build_time_groups(self.db, gap_hours=6.0)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["file_ids"], [fid])
        self.assertIsNotNone(group["start_time"])
        self.assertTrue(group["suggested_name"])
        self.assertEqual(len(group["items"]), 1)
        self.assertEqual(group["items"][0]["id"], fid)

    def test_max_items_per_group_limits_items(self):
        for i in range(5):
            self._insert(f"img{i}.jpg", BASE_TS + i * 60)
        groups = organize_service.build_time_groups(self.db, gap_hours=6.0, max_items_per_group=2)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 5)
        self.assertEqual(len(groups[0]["items"]), 2)
        self.assertEqual(len(groups[0]["file_ids"]), 5)

    def test_trash_files_excluded(self):
        self._insert("a.jpg", BASE_TS)
        fid_b = self._insert("b.jpg", BASE_TS + 60)
        self.db.set_trash_folder(os.path.join(self.temp_dir, "trash"))
        self.assertTrue(self.db.move_to_trash(fid_b))
        groups = organize_service.build_time_groups(self.db, gap_hours=6.0)
        all_ids = [fid for g in groups for fid in g["file_ids"]]
        self.assertNotIn(fid_b, all_ids)


class TestApplyGroups(_OrganizeTestBase):
    def test_moves_files_into_named_folders(self):
        fid_a = self._insert("a.jpg", BASE_TS)
        fid_b = self._insert("b.jpg", BASE_TS + 60)
        dest_root = os.path.join(self.temp_dir, "organized")
        result = organize_service.apply_groups(
            self.db, dest_root, [{"name": "2023-11-15", "file_ids": [fid_a, fid_b]}]
        )
        self.assertEqual(result["moved"], 2)
        self.assertEqual(result["failed_ids"], [])
        folder = os.path.join(dest_root, "2023-11-15")
        self.assertTrue(os.path.isdir(folder))
        self.assertTrue(os.path.exists(os.path.join(folder, "a.jpg")))
        # DB のパスも更新されている
        row = self.db.get_file_by_id(fid_a)
        self.assertEqual(os.path.normpath(os.path.dirname(row["path"])), os.path.normpath(folder))
        self.assertEqual(row["status"], "sorted")

    def test_invalid_name_sanitized(self):
        fid = self._insert("a.jpg", BASE_TS)
        dest_root = os.path.join(self.temp_dir, "organized")
        result = organize_service.apply_groups(
            self.db, dest_root, [{"name": 'bad<name>?', "file_ids": [fid]}]
        )
        self.assertEqual(result["moved"], 1)
        self.assertTrue(result["folders"][0]["path"].endswith("bad_name__"))

    def test_missing_and_trash_files_reported_as_failed(self):
        fid = self._insert("a.jpg", BASE_TS)
        self.db.set_trash_folder(os.path.join(self.temp_dir, "trash"))
        self.assertTrue(self.db.move_to_trash(fid))
        dest_root = os.path.join(self.temp_dir, "organized")
        result = organize_service.apply_groups(
            self.db, dest_root, [{"name": "g", "file_ids": [fid, 99999]}]
        )
        self.assertEqual(result["moved"], 0)
        self.assertEqual(sorted(result["failed_ids"]), sorted([fid, 99999]))

    def test_multiple_groups(self):
        fid_a = self._insert("a.jpg", BASE_TS)
        fid_b = self._insert("b.jpg", BASE_TS + 60)
        dest_root = os.path.join(self.temp_dir, "organized")
        result = organize_service.apply_groups(
            self.db,
            dest_root,
            [
                {"name": "旅行", "file_ids": [fid_a]},
                {"name": "仕事", "file_ids": [fid_b]},
            ],
        )
        self.assertEqual(result["moved"], 2)
        self.assertEqual(len(result["folders"]), 2)
        self.assertTrue(os.path.exists(os.path.join(dest_root, "旅行", "a.jpg")))
        self.assertTrue(os.path.exists(os.path.join(dest_root, "仕事", "b.jpg")))


if __name__ == "__main__":
    unittest.main()

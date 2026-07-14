"""
/api/organize エンドポイントの統合テスト（FastAPI TestClient 使用）。
fastapi / httpx が未導入の環境ではスキップする。
"""
import unittest
import os
import shutil
import sys
import tempfile
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi.testclient import TestClient
    from src import api_server
    from src.database import DatabaseManager
    DEPS_AVAILABLE = True
    IMPORT_ERROR = ""
except ImportError as exc:  # fastapi / httpx / cv2 が無い環境
    DEPS_AVAILABLE = False
    IMPORT_ERROR = str(exc)

logging.basicConfig(level=logging.WARNING)

HOUR = 3600.0
BASE_TS = 1700000000.0


@unittest.skipUnless(DEPS_AVAILABLE, f"api deps not installed: {IMPORT_ERROR}")
class TestOrganizeApi(unittest.TestCase):
    """テスト用の一時 DB に差し替えて organize API を検証する"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_photos.db")
        self._original_db = api_server.db
        api_server.db = DatabaseManager(self.test_db_path)
        self.client = TestClient(api_server.app)

    def tearDown(self):
        api_server.db.close()
        api_server.db = self._original_db
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _insert(self, name: str, mtime: float) -> int:
        path = os.path.join(self.temp_dir, name)
        with open(path, "w") as fp:
            fp.write("x")
        api_server.db.insert_file(path, 100, mtime)
        return api_server.db.get_file_id_by_path(path)

    def test_capabilities(self):
        res = self.client.get("/api/organize/capabilities")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["time"])
        self.assertIn("content", body)
        self.assertIn("ai_dependencies_installed", body)

    def test_preview_groups_by_gap(self):
        self._insert("a.jpg", BASE_TS)
        self._insert("b.jpg", BASE_TS + HOUR)
        self._insert("c.jpg", BASE_TS + 24 * HOUR)
        res = self.client.get("/api/organize/preview", params={"gap_hours": 6})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["groups"]), 2)
        self.assertEqual(sorted(g["count"] for g in body["groups"]), [1, 2])

    def test_preview_min_group_size(self):
        self._insert("a.jpg", BASE_TS)
        self._insert("b.jpg", BASE_TS + HOUR)
        self._insert("c.jpg", BASE_TS + 24 * HOUR)
        res = self.client.get(
            "/api/organize/preview", params={"gap_hours": 6, "min_group_size": 2}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["groups"]), 1)

    def test_preview_validation(self):
        res = self.client.get("/api/organize/preview", params={"gap_hours": 0})
        self.assertEqual(res.status_code, 422)

    def test_apply_moves_files(self):
        fid_a = self._insert("a.jpg", BASE_TS)
        fid_b = self._insert("b.jpg", BASE_TS + 60)
        dest_root = os.path.join(self.temp_dir, "organized")
        res = self.client.post(
            "/api/organize/apply",
            json={
                "destination_root": dest_root,
                "groups": [{"name": "2023-11-15", "file_ids": [fid_a, fid_b]}],
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["moved"], 2)
        self.assertEqual(body["failed_ids"], [])
        self.assertTrue(os.path.exists(os.path.join(dest_root, "2023-11-15", "a.jpg")))

    def test_apply_rejects_missing_destination(self):
        fid = self._insert("a.jpg", BASE_TS)
        res = self.client.post(
            "/api/organize/apply",
            json={
                "destination_root": os.path.join(self.temp_dir, "no", "such", "deep"),
                "groups": [{"name": "g", "file_ids": [fid]}],
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_apply_rejects_empty_groups(self):
        res = self.client.post(
            "/api/organize/apply",
            json={"destination_root": self.temp_dir, "groups": []},
        )
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()

"""
_similar_groups（pHash 類似グループ化）のテスト。
numpy でベクトル化した実装が、素朴なハミング距離計算と同じ結果になることを担保する。
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.utils import hamming_dist


def naive_groups(items, distance):
    """修正前と同じ素朴な貪欲グルーピング（期待値の基準）"""
    visited = set()
    groups = []
    for item in items:
        if item["id"] in visited:
            continue
        members = [o for o in items
                   if o["id"] not in visited and hamming_dist(item["hash"], o["hash"]) <= distance]
        if len(members) < 2:
            continue
        for m in members:
            visited.add(m["id"])
        groups.append([m["id"] for m in members])
    return groups


class TestSimilarGroups(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = DatabaseManager(os.path.join(self.temp_dir, "t.db"))
        import src.api_server as srv
        self.srv = srv
        self._orig_db = srv.db
        srv.db = self.db

    def tearDown(self):
        self.srv.db = self._orig_db
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _add(self, name: str, phash: str) -> int:
        path = os.path.join(self.temp_dir, name)
        with open(path, "w") as fp:
            fp.write("x")
        self.db.insert_file(path, 10, 1234567890.0)
        fid = self.db.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()[0]
        self.db.update_analysis_result(fid, "q", phash, 10.0)
        return fid

    def test_identical_hashes_group_together(self):
        a = self._add("a.jpg", "ffffffffffffffff")
        b = self._add("b.jpg", "ffffffffffffffff")
        self._add("c.jpg", "0000000000000000")
        groups, scanned, available = self.srv._similar_groups(distance=2, max_items=100)
        self.assertEqual(scanned, 3)
        self.assertEqual(available, 3)
        self.assertEqual(len(groups), 1)
        self.assertCountEqual([i["id"] for i in groups[0]["items"]], [a, b])

    def test_distance_boundary_is_inclusive(self):
        # 1 ビットだけ違う
        self._add("a.jpg", "0000000000000000")
        self._add("b.jpg", "0000000000000001")
        self.assertEqual(len(self.srv._similar_groups(distance=1, max_items=100)[0]), 1)
        self.assertEqual(len(self.srv._similar_groups(distance=0, max_items=100)[0]), 0)

    def test_matches_naive_implementation(self):
        """ランダムなハッシュ集合で素朴実装と一致すること"""
        import random
        random.seed(20260812)
        items = []
        for i in range(60):
            h = random.getrandbits(64)
            fid = self._add(f"f{i}.jpg", f"{h:016x}")
            items.append({"id": fid, "hash": h})

        for distance in (0, 3, 8, 16):
            expected = naive_groups(items, distance)
            groups, _scanned, _available = self.srv._similar_groups(distance=distance, max_items=100)
            actual = [[i["id"] for i in g["items"]] for g in groups]
            self.assertEqual(len(actual), len(expected), f"distance={distance} のグループ数が不一致")
            for got, want in zip(actual, expected):
                self.assertCountEqual(got, want, f"distance={distance} のメンバーが不一致")

    def test_empty_phash_is_ignored(self):
        """解析スキップ分（空文字）は候補にしない"""
        path = os.path.join(self.temp_dir, "skipped.mp4")
        with open(path, "w") as fp:
            fp.write("x")
        self.db.insert_file(path, 10, 1234567890.0)
        fid = self.db.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()[0]
        self.db.update_analysis_result(fid, "q", "", 0.0)
        groups, scanned, available = self.srv._similar_groups(distance=5, max_items=100)
        self.assertEqual((len(groups), scanned, available), (0, 0, 0))

    def test_max_items_truncation_is_reported(self):
        for i in range(5):
            self._add(f"f{i}.jpg", "ffffffffffffffff")
        groups, scanned, available = self.srv._similar_groups(distance=2, max_items=3)
        self.assertEqual(scanned, 3)
        self.assertEqual(available, 5)
        self.assertEqual(groups[0]["count"], 3)

    def test_no_group_for_single_file(self):
        self._add("solo.jpg", "abcdefabcdefabcd")
        self.assertEqual(self.srv._similar_groups(distance=5, max_items=100)[0], [])


if __name__ == '__main__':
    unittest.main()

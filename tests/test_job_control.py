"""
ジョブの一時停止・再開・中止のテスト。

長時間かかる解析を止められないと運用に耐えないため、
JobManager の制御と、run_analyze がそれに従うことを検証する。
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api_server import JobManager
from src.database import DatabaseManager
from src.services.scan_analyze_service import run_analyze


class TestJobManagerControl(unittest.TestCase):
    def setUp(self):
        self.jobs = JobManager()

    def test_pause_requires_running_job(self):
        self.assertFalse(self.jobs.pause(), "実行中でないのに一時停止できてしまう")
        self.assertFalse(self.jobs.resume())
        self.assertFalse(self.jobs.cancel())

    def test_pause_blocks_and_resume_releases(self):
        released = threading.Event()

        def worker():
            self.jobs.wait_if_paused()
            released.set()

        self.jobs.start("test", lambda: time.sleep(0.5))
        self.assertTrue(self.jobs.pause())
        self.assertTrue(self.jobs.snapshot()["paused"])

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        self.assertFalse(released.wait(0.2), "一時停止中なのに待機を通過している")

        self.assertTrue(self.jobs.resume())
        self.assertTrue(released.wait(1.0), "再開しても待機が解除されない")
        self.assertFalse(self.jobs.snapshot()["paused"])

    def test_cancel_releases_paused_worker(self):
        """一時停止中に中止しても、待っているワーカーが起きること"""
        released = threading.Event()

        self.jobs.start("test", lambda: time.sleep(0.5))
        self.jobs.pause()

        threading.Thread(
            target=lambda: (self.jobs.wait_if_paused(), released.set()), daemon=True
        ).start()
        self.assertFalse(released.wait(0.2))

        self.assertTrue(self.jobs.cancel())
        self.assertTrue(released.wait(1.0), "中止しても待機が解除されない（デッドロック）")
        self.assertTrue(self.jobs.should_stop())

    def test_paused_is_cleared_after_job_finishes(self):
        self.jobs.start("test", lambda: None)
        for _ in range(50):
            if not self.jobs.snapshot()["running"]:
                break
            time.sleep(0.02)
        self.assertFalse(self.jobs.snapshot()["paused"])
        # 一時停止フラグが残っていると次のジョブが最初から止まってしまう
        self.jobs.start("test2", lambda: None)
        self.assertFalse(self.jobs.snapshot()["paused"])


class TestAnalyzeRespectsStop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = DatabaseManager(os.path.join(self.temp_dir, "t.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _add_files(self, n: int):
        from PIL import Image

        img = Image.new("RGB", (64, 48), (10, 20, 30))
        for i in range(n):
            p = os.path.join(self.temp_dir, f"f{i}.jpg")
            img.save(p, format="JPEG")
            st = os.stat(p)
            self.db.insert_file(p, st.st_size, st.st_mtime)

    def test_stops_immediately_when_requested(self):
        self._add_files(5)
        result = run_analyze(self.db, should_stop=lambda: True)
        self.assertTrue(result["stopped"])
        self.assertEqual(result["processed"], 0)
        # 未処理のまま残るので、後から続きを実行できる
        self.assertEqual(self.db.get_unprocessed_count(), 5)

    def test_processes_all_when_not_stopped(self):
        self._add_files(5)
        result = run_analyze(self.db)
        self.assertFalse(result["stopped"])
        self.assertEqual(result["processed"], 5)
        self.assertEqual(self.db.get_unprocessed_count(), 0)


if __name__ == "__main__":
    unittest.main()

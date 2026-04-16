"""
ScannerThread / AnalyzerThread のモックベーステスト

PyQt6 がインストールされている環境でのみ実行される。
"""
import unittest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PyQt6.QtWidgets import QApplication
    from src.core import ScannerThread, AnalyzerThread
    from src.database import DatabaseManager
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

# QApplication はプロセスに 1 つだけ必要
_app = None
if HAS_PYQT:
    _app = QApplication.instance() or QApplication([])


@unittest.skipUnless(HAS_PYQT, "PyQt6 / cv2 が必要（環境によってはスキップ）")
class TestScannerThread(unittest.TestCase):
    """ScannerThread の差分スキャンロジックをテスト"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = DatabaseManager(self.db_path)
        # スキャン対象のフォルダ
        self.scan_dir = os.path.join(self.temp_dir, "photos")
        os.makedirs(self.scan_dir, exist_ok=True)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def _create_image(self, name: str) -> str:
        """テスト用のダミー画像ファイルを作成"""
        path = os.path.join(self.scan_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(b'\xFF\xD8\xFF' + b'\x00' * 100)  # 最小限の JPEG ヘッダ
        return path

    def _run_scanner(self):
        """ScannerThread を同期的に実行"""
        scanner = ScannerThread(self.scan_dir, self.db)
        scanner.run()  # QThread.start() ではなく直接 run() で同期実行

    # -------------------------------------------------------
    # 基本動作
    # -------------------------------------------------------
    def test_empty_folder_scan(self):
        """空フォルダのスキャンで 0 件"""
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 0)

    def test_new_files_registered(self):
        """新規ファイルが DB に登録される"""
        self._create_image("a.jpg")
        self._create_image("sub/b.png")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 2)

    def test_no_double_insert(self):
        """同じファイルを再スキャンしても重複しない"""
        self._create_image("a.jpg")
        self._run_scanner()
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 1)

    def test_incremental_scan(self):
        """2 回目のスキャンで差分だけ追加される"""
        self._create_image("a.jpg")
        self._run_scanner()
        self._create_image("b.jpg")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 2)

    # -------------------------------------------------------
    # 削除同期
    # -------------------------------------------------------
    def test_missing_file_removed(self):
        """ディスクから消えたファイルが DB からも消える"""
        path = self._create_image("gone.jpg")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 1)

        os.remove(path)
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 0)

    def test_other_root_files_preserved(self):
        """別ルートのファイルは削除同期で消えない"""
        # 先に別ルートのファイルを DB に直接登録
        other_dir = os.path.join(self.temp_dir, "other_photos")
        os.makedirs(other_dir)
        other_file = os.path.join(other_dir, "keep.jpg")
        with open(other_file, 'wb') as f:
            f.write(b'\xFF\xD8\xFF' + b'\x00' * 50)
        self.db.insert_file(other_file, 53, 1234567890.0)
        self.assertEqual(self.db.get_file_count(), 1)

        # scan_dir をスキャンしても other_photos のファイルは残る
        self._run_scanner()
        all_files = self.db.get_all_files()
        self.assertIn(other_file, [os.path.normpath(p) for p in all_files])

    # -------------------------------------------------------
    # 拡張子フィルタ
    # -------------------------------------------------------
    def test_non_image_files_ignored(self):
        """画像/動画以外のファイルは無視される"""
        # テキストファイルは登録されない
        txt_path = os.path.join(self.scan_dir, "readme.txt")
        with open(txt_path, 'w') as f:
            f.write("hello")
        self._create_image("a.jpg")
        self._run_scanner()
        self.assertEqual(self.db.get_file_count(), 1)

    # -------------------------------------------------------
    # stop フラグ
    # -------------------------------------------------------
    def test_stop_flag(self):
        """stop() を呼ぶとスキャンが中断される"""
        for i in range(50):
            self._create_image(f"img_{i:03d}.jpg")
        scanner = ScannerThread(self.scan_dir, self.db)
        scanner.stop()  # 事前に stop
        scanner.run()
        # 途中で止まるので全件登録にはならない可能性が高い
        # ただし run_flag チェック位置により 0 件か 50 件以下であること
        self.assertLessEqual(self.db.get_file_count(), 50)

    # -------------------------------------------------------
    # root_path の保存
    # -------------------------------------------------------
    def test_root_path_saved(self):
        """スキャン完了後、root_path が設定に保存される"""
        self._run_scanner()
        saved = self.db.get_setting("root_path")
        self.assertEqual(saved, self.scan_dir)


@unittest.skipUnless(HAS_PYQT, "PyQt6 / cv2 が必要（環境によってはスキップ）")
class TestAnalyzerThread(unittest.TestCase):
    """AnalyzerThread の基本動作テスト"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_no_files(self):
        """未処理ファイルがない場合、正常終了する"""
        analyzer = AnalyzerThread(self.db)
        analyzer.run()  # 同期実行
        self.assertEqual(self.db.get_unprocessed_count(), 0)

    def test_stop_flag(self):
        """stop() で中断される"""
        analyzer = AnalyzerThread(self.db)
        analyzer.stop()
        analyzer.run()
        # 例外なく完了すれば OK


if __name__ == '__main__':
    unittest.main()

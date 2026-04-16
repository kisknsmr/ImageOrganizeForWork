"""
テスト実行スクリプト
.venv環境を使用してテストを実行します
"""
import sys
import os
import unittest

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

if __name__ == '__main__':
    # テストディスカバリー
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.dirname(os.path.abspath(__file__)), pattern='test_*.py')
    
    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 終了コード
    sys.exit(0 if result.wasSuccessful() else 1)

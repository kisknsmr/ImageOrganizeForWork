# PhotoSortX - プログラム完成度評価（2026-02-15 更新）

## 概要

| 項目 | 値 |
|------|----|
| Python ファイル数 | 24 |
| 総コード行数 | 約 7,500 行 |
| テストケース数 | 35 |
| パッケージ構成 | `src/`（コア）、`gui/`（GUI部品）、`modules/`（機能UI）、`tests/` |

---

## A. 完成度が高い点

| カテゴリ | 内容 |
|----------|------|
| **機能の網羅性** | スキャン・解析・重複/ピンボケ/類似整理・手動仕分け・AI分類（CLIP）・小さいファイル削除・削除済み一覧まで一通り実装されている |
| **パッケージ構成** | `src/` に config/database/core を集約、モジュールの import パスが統一されている |
| **差分更新** | `path_under_root` による誤削除防止、別フォルダ選択時の自動置き換え、実パス解決+normcase による同一フォルダ判定 |
| **エラーハンドリング** | 全モジュールで `try-except` が適切に使われ、bare `except` なし。sqlite3.Error / OSError 等の特定例外を捕捉してログ記録 |
| **スレッドセーフ** | DatabaseManager に RLock、スキャン/解析は QThread で非同期。ボタンロックで二重実行を防止 |
| **設定の一元化** | `src/config.py` の dataclass で全設定を管理、パス検証も組み込み |
| **依存管理** | requirements.txt に全依存が揃っており、未使用の依存なし |
| **closeEvent** | `main.py` で DB 接続を close しており、リソースリークなし |

---

## B. 不足点・バグ・改善すべき点

### B-1. バグ（修正済み / 要修正）

| # | 深刻度 | 内容 | 状態 |
|---|--------|------|------|
| 1 | **致命的** | `main.py` の `on_loaded` 内で `TrashListPage` が `global` 宣言されていなかった。モジュールレベルの `TrashListPage` が `None` のまま `MainWindow.__init__` で `TrashListPage(self.db)` が呼ばれ、起動時に `TypeError` でクラッシュする | **修正済み** |

### B-2. ドキュメント

| # | 優先度 | 内容 |
|---|--------|------|
| 2 | 高 | **README のプロジェクト構造が古い** — `core.py` / `database.py` / `config.py` がルートにあると記載。実際は `src/` 配下に移動済み |
| 3 | 高 | **README の依存バージョンが古い** — README に記載されたバージョン（numpy 1.26.4 等）と requirements.txt（numpy 2.4.0 等）が全 7 件で不一致 |
| 4 | 中 | **バージョン番号の不一致** — README タイトルと `main.py` のウィンドウタイトルは `v2.2`、README の更新履歴には `v2.3` がある |
| 5 | 中 | **AI_SETUP_GUIDE.md のパスが古い** — `config.py を編集` と記載されている 6 箇所が `src/config.py` に更新されていない |
| 6 | 低 | **ライセンスが未記載** — README に「ここに記載してください」とあるのみ。LICENSE ファイルなし |
| 7 | 低 | **CHANGELOG の分離** — 更新履歴が README 内にあり、CHANGELOG.md として独立させると管理しやすい |
| 8 | 低 | **API・モジュール仕様書がない** — 各モジュールの責務・公開関数を説明する開発者向けドキュメントがない |

### B-3. リポジトリ・プロジェクト設定

| # | 優先度 | 内容 |
|---|--------|------|
| 9 | **高** | **ルート .gitignore がない** — `__pycache__/`, `*.pyc`, `photos.db`, `photos.db-shm`, `photos.db-wal`, `debug.log`, `.venv/`, `.idea/`, `.cursor/` 等を除外する .gitignore が存在しない。git status で不要ファイルが大量に表示される |
| 10 | 中 | **pyproject.toml がない** — パッケージ名・バージョン・エントリポイント・ツール設定（ruff / mypy 等）が管理されていない |
| 11 | 低 | **バージョン番号が散在** — `main.py` ウィンドウタイトル・README に「v2.2」がハードコードされている。`pyproject.toml` の `version` から参照すると一元化できる |

### B-4. コード品質

| # | 優先度 | 内容 |
|---|--------|------|
| 12 | 中 | **modules/ の `sys.path.append` が冗長** — `duplicate_ui.py`, `blur_ui.py`, `similarity_ui.py`, `sorter_ui.py`, `manual_sorter_ui.py`, `small_file_cleaner_ui.py` の計 6 ファイルに `sys.path.append(os.path.dirname(os.path.dirname(...)))` がある。`main.py` からの起動時にはプロジェクトルートが `sys.path[0]` に入るため不要。単体実行にも必要ないなら除去する方がよい |
| 13 | 低 | **`small_file_cleaner_ui.py` の削除失敗時にエラーメッセージが出ない** — 他の UI モジュール（duplicate, blur, similarity, trash_list）は削除失敗時に `QMessageBox.warning` を表示するが、small_file_cleaner のみメッセージなし |
| 14 | 低 | **ログローテーション未設定** — `debug.log` に追記のみで、サイズ/世代数の制限がない。長期運用でファイルが肥大化する。`RotatingFileHandler` への置き換えを推奨 |

### B-5. テスト

| # | 優先度 | 内容 |
|---|--------|------|
| 15 | 高 | **`test_core.py` が cv2 未インストール環境で全テスト失敗** — `from src.core import ...` が cv2 を引き込むため、cv2 がない環境ではテストスイート自体が読み込めない。軽い関数（`format_eta`, `hamming_dist` 等）を別モジュールに分離するか、cv2 を import 時にモックするとよい |
| 16 | 中 | **DatabaseManager のテストカバレッジが低い** — 全 30+ メソッドのうちテストがあるのは 11 メソッドのみ。未テストの主要メソッド: `get_all_files`, `move_to_trash`, `move_file_to_folder`, `get_duplicate_hashes`, `get_blurry_files`, `update_analysis_result`, `get_trash_files`, `permanently_delete_file`, カスタムカテゴリ関連 5 メソッド |
| 17 | 中 | **ScannerThread / AnalyzerThread のテストがない** — ディスク走査・差分削除・解析パイプラインの統合テストがなく、ロジック変更時のリグレッション検出ができない |
| 18 | 低 | **GUI / ワークフローの E2E テストがない** — 起動→スキャン→解析→画面遷移の自動検証がない |
| 19 | 低 | **`format_file_size_kb` のテストがない** — `format_file_size` はテスト済みだが、KB 版は未テスト |

### B-6. セキュリティ・堅牢性

| # | 優先度 | 内容 |
|---|--------|------|
| 20 | 低 | **`ALLOWED_PATH_PREFIXES` が実質未使用** — `config.validate_path` 内で参照されるが、デフォルトが空タプルのため常に通過する。利用するなら設定例とドキュメントが必要 |

### B-7. パフォーマンス・UX

| # | 優先度 | 内容 |
|---|--------|------|
| 21 | 低 | **大量ファイル時のギャラリー仮想化** — 件数が極端に多い場合のリスト仮想化・ページングが未確認 |
| 22 | 低 | **国際化（i18n）なし** — すべての文言が日本語でハードコード。多言語対応するなら Qt の `tr()` や gettext の導入が必要 |
| 23 | 低 | **キーボードショートカットの明示** — ドキュメント・ヘルプにまとまっていない |

### B-8. CI/CD・開発フロー

| # | 優先度 | 内容 |
|---|--------|------|
| 24 | 低 | **CI がない** — GitHub Actions 等でテスト・リントを自動実行する設定がない |
| 25 | 低 | **リント・フォーマッタ未設定** — ruff / black / flake8 等の設定ファイルがなく、コードスタイルの統一が手動 |
| 26 | 低 | **型チェック未導入** — 型ヒントは一部で使われているが、mypy / pyright のチェックは行われていない |

### B-9. その他

| # | 優先度 | 内容 |
|---|--------|------|
| 27 | 低 | **AI 依存のオプション化** — `torch` / `transformers` が requirements.txt に必須で並んでいる。AI を使わないユーザー向けにエクストラ依存（`pip install .[ai]`）に分離するとインストールが軽くなる |

---

## C. テストカバレッジ概況

### テスト済み

| モジュール | テスト済みの関数・メソッド |
|------------|--------------------------|
| `src/config.py` | `validate_path` (4 パターン), `get_default_trash_folder`, `ALL_EXTENSIONS`, デフォルト値 |
| `src/database.py` | `init_db`, `insert_file`, `get_file_count`, `get_unprocessed_count`, `set_setting`, `get_setting`, `save_thumbnail`, `get_thumbnail`, `remove_files`, `rebuild_db`, パス検証 |
| `src/core.py` | `format_eta`, `hamming_dist`, `format_file_size`, `get_capture_time`, `get_file_info`, `path_under_root` (6 パターン) |

### 未テスト（主要なもの）

| モジュール | 未テストの関数・メソッド |
|------------|--------------------------|
| `src/core.py` | `setup_logging`, `create_error_pixmap`, `get_db_thumbnail`, `get_preview_image`, `format_file_size_kb`, `ScannerThread`, `AnalyzerThread`, `ImageLoader` |
| `src/database.py` | `get_all_files`, `get_all_files_with_info`, `move_to_trash`, `move_file_to_folder`, `get_duplicate_hashes`, `get_files_by_hash`, `get_blurry_files`, `get_files_with_phash`, `update_analysis_result`, `get_trash_files`, `delete_file_record`, `permanently_delete_file`, カスタムカテゴリ関連 5 メソッド |
| GUI / modules | テストなし（全モジュール） |

---

## D. 優先度まとめ

| 優先度 | 対象 |
|--------|------|
| **高（すぐ対応）** | `.gitignore` 追加（#9）、README のプロジェクト構造更新（#2）、README の依存バージョン更新（#3）、`test_core` の cv2 依存対策（#15） |
| **中（早めに）** | `sys.path.append` の除去（#12）、バージョン番号統一（#4, #11）、AI_SETUP_GUIDE パス修正（#5）、DB メソッドのテスト追加（#16）、Scanner/Analyzer のテスト追加（#17）、pyproject.toml 導入（#10） |
| **低（余裕があれば）** | ログローテーション（#14）、ライセンス（#6）、CHANGELOG 分離（#7）、i18n（#22）、CI（#24）、リント設定（#25）、型チェック（#26）、AI 依存オプション化（#27）等 |

---

## E. 総評

### スコア（5段階）

| 項目 | 評価 | 備考 |
|------|------|------|
| 機能完成度 | ★★★★☆ | 主要機能はすべて実装されている。AI 分類まで含めて実用レベル |
| コード品質 | ★★★★☆ | エラーハンドリング・スレッドセーフ・パス検証が整っている。bare except なし |
| テスト | ★★☆☆☆ | config / database の基本操作はカバー。コアクラス（Scanner/Analyzer）、DB の高度な操作、GUI は未テスト |
| ドキュメント | ★★☆☆☆ | README は詳細だが、ファイル構成・バージョン・依存バージョンが実態と不一致 |
| リポジトリ管理 | ★☆☆☆☆ | .gitignore なし、pyproject.toml なし、CI なし。DB・ログファイルが git に混入 |

### 一言

**アプリケーションとしての完成度は高い。** 機能は一通り揃い、差分更新・パス安全・スレッド安全も対応済み。不足しているのは主に「運用・開発インフラ」（.gitignore、ドキュメント整合、テストカバレッジ、CI）であり、これらを補えば配布・チーム開発にも耐えうる品質になる。

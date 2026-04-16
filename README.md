# PhotoSortX（v2.3）

AI を併用できる画像整理・管理用デスクトップアプリ（PyQt6）です。フォルダ同期、解析、重複・ピンボケ・類似の整理、手動仕分け、スマート整理（CLIP）などをまとめて扱えます。

## 主な機能

| 区分 | 内容 |
|------|------|
| メイン | フォルダ同期（Scan）、詳細解析（Analyze）、ギャラリー |
| クリーンアップ | 重複（MD5）、ピンボケ（Laplacian）、類似（pHash + VP-Tree）、極小ファイル削除 |
| 整理 | 手動仕分け、スマート整理（イベントグルーピング + CLIP）、削除済み一覧 |

## デザイン

`src/theme.py` でトークン管理する **ダーク UI**（例: 背景 `#242424`、サイドバー `#1a1a1a`、アクセント青）です。リポジトリ同梱の可変フォント（`fonts/` の Inter / Noto Sans JP / Roboto）を読み込み、利用可能なら UI フォントに使います。

## 要件

- **Python 3.10 以上**（`pyproject.toml` の `requires-python` に準拠）
- Windows を主対象にしていますが、PyQt6 が動く環境であれば他 OS も想定できます
- AI（スマート整理）利用時は **GPU なしでも可**ですが、メモリ・ディスクに余裕があると安全です（初回はモデル取得でネットワークが必要な場合があります）

## セットアップ

```bash
git clone <repository-url>
cd ImageOrganizeForWork
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### AI（任意）

`requirements.txt` には含めていません（コアのみ軽量化）。スマート整理を使う場合は例えば次で追加します。

```bash
pip install "torch>=2.2" "transformers>=4.37"
```

または開発用にリポジトリから一括:

```bash
pip install -e ".[ai]"
```

詳細は [AI_SETUP_GUIDE.md](AI_SETUP_GUIDE.md) を参照してください。

### パッケージとして入れる場合

```bash
pip install -e .
```

コンソールエントリ `photosortx` が有効になります（依存関係は別途 `pip install -r requirements.txt` などで入れてください）。フォントはリポジトリの `fonts/` を参照するため、**配布 zip 利用時は `fonts` をアプリと同じ階層に含める**か、開発と同様にリポジトリ全体を配置してください。

## 起動

```bash
python main.py
```

インストール済みの場合:

```bash
photosortx
```

## ログ

`src/config.py` の `LOG_LEVEL`（既定は `DEBUG`）と `LOG_FILE`（既定 `debug.log`）で制御します。ローテーション付きファイル出力とコンソール出力を使い分けます。本番利用時は `INFO` などへの変更を推奨します。

## 設定・データ

- 設定の定数・既定値: `src/config.py` の `AppConfig`（インスタンス `config`）
- SQLite: 既定でカレントディレクトリの `photos.db`（`config.DB_NAME`）

## プロジェクト構成（抜粋）

```
ImageOrganizeForWork/
├── main.py                 # エントリ（起動・メインウィンドウ）
├── pyproject.toml          # メタデータ・任意依存 ai・ビルド設定
├── requirements.txt        # コア依存のみ
├── MANIFEST.in             # sdist 用（フォント等）
├── fonts/                  # UI 用フォント（任意）
├── src/
│   ├── config.py
│   ├── core.py             # スキャン・解析・画像 I/O
│   ├── database.py
│   ├── theme.py
│   └── utils.py
├── gui/
│   ├── gallery_page.py
│   ├── icons.py
│   ├── models.py
│   ├── splash.py
│   ├── thumbnail_preview.py
│   └── workers.py          # 遅延ロード（起動を速くする）
├── modules/                # 各機能ページ UI
└── tests/                  # unittest（python tests/run_tests.py）
```

## テスト

```bash
python tests/run_tests.py
```

（`pytest` 未導入でも上記で全テストを実行できます。）

## トラブルシューティング（要約）

| 現象 | 確認 |
|------|------|
| AI が動かない | `torch` / `transformers` の導入、初回モデル取得、オフライン時は `HF_OFFLINE_MODE` など `src/config.py` |
| メモリ不足 | バッチ系定数の縮小、AI 未使用なら AI パッケージを外す |
| 遅い | `LOW_LOAD_MODE`、DB の整理、不要データの削減 |

## ライセンス・履歴

- ライセンス: [LICENSE](LICENSE)（MIT）
- 更新履歴: [CHANGELOG.md](CHANGELOG.md)

## 謝辞

PyQt6、OpenCV、Pillow、scikit-learn、CLIP / Hugging Face エコシステムを利用しています。

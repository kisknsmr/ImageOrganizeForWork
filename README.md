# PhotoSortX（v2.3）

AI を併用できる画像整理・管理アプリです。**デスクトップ UI は Tauri + React（`app/`）**、フォルダ走査・DB・解析は **Python の FastAPI（`src/api_server.py`）** が担当します。

## 主な機能

| 区分 | 内容 |
|------|------|
| メイン | フォルダ同期（Scan）、詳細解析（Analyze）、ギャラリー |
| クリーンアップ | 重複（MD5）、ピンボケ（Laplacian）、類似（pHash）、極小ファイル削除（順次） |
| 整理 | トリアージ、手動仕分け、スマート整理（順次）、削除済み一覧 |

## 要件

- **Python 3.10 以上**
- デスクトップ UI: **Node.js**（Tauri / Vite ビルド用）
- Windows を主対象としています
- AI（CLIP 等）利用時は **GPU なしでも可**ですが、メモリ・ディスクに余裕があると安全です

## セットアップ（Python API）

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

### パッケージとして入れる場合

```bash
pip install -e .
```

コンソールエントリ **`photosortx-api`** で API サーバーを起動できます（既定 `127.0.0.1:8765`）。

## AI（任意・CLIP 等）

コアの `requirements.txt` には含めていません。利用する場合:

```bash
pip install "torch>=2.2" "transformers>=4.37"
# または
pip install -e ".[ai]"
```

**Hugging Face に繋がらない場合**（タイムアウト・中国圏など）は `src/config.py` で次を調整します。

| 目的 | 設定例 |
|------|--------|
| 一度ダウンロードしたモデルだけ使う | `HF_OFFLINE_MODE: bool = True` |
| ミラー経由で取得 | `HF_MIRROR_SITE: str = "https://hf-mirror.com"` |
| キャッシュ場所を固定 | `HF_MODEL_CACHE_DIR: str = "C:/models/huggingface"` |

プロキシが必要な環境では `HTTP_PROXY` / `HTTPS_PROXY` を設定してから起動します。GPU メモリ不足のときは `src/config.py` のバッチ系定数を小さくするか CPU で実行してください。

## 起動

1. **API サーバー**（プロジェクトルート）:

```bash
photosortx-api
```

または:

```bash
uvicorn src.api_server:app --host 127.0.0.1 --port 8765
```

2. **デスクトップアプリ**（`app/`）:

```bash
cd app
npm install
npm run tauri dev
```

## ログ・設定・データ

- ログ: `src/config.py` の `LOG_LEVEL`（既定 `DEBUG`）、`LOG_FILE`（既定 `debug.log`）。ローテーション付きファイル出力とコンソール出力
- 定数・既定値: `src/config.py` の `AppConfig`（インスタンス `config`）
- SQLite: 既定でカレントディレクトリの `photos.db`（`config.DB_NAME`）

## 本番データを触る前に

| 操作 | ディスク上の写真 |
|------|------------------|
| スキャン | 削除しない（DB の登録のみ） |
| スキャン開始時の実在確認 | 実在しないパスの **DB 行だけ** 削除 |
| ゴミ箱へ移動 | 指定フォルダから **削除用フォルダへ移動** |
| 完全削除（許可時） | **ファイルを削除**（退避期間・設定に依存） |
| DB 全初期化 | **画像ファイルは触らない**（DB 等のみ） |

- `TRASH_RETENTION_DAYS`（既定 14 日）と `ENFORCE_TRASH_RETENTION_BEFORE_PERMANENT_DELETE` は `src/config.py` を参照
- NAS 等ではパスが一瞬見えないと「存在しない」扱いで DB が整理されることがあるため、**マウント安定後に同期**することを推奨
- 大量スキャン時は `LOW_LOAD_MODE = True` で I/O 負荷を下げられます（所要時間は伸びます）
- 初回は **写真のコピー先** と **空またはテスト用 DB** で操作を一通り試すと安全です

## プロジェクト構成（抜粋）

```
ImageOrganizeForWork/
├── app/                    # Tauri + React フロントエンド
├── pyproject.toml
├── requirements.txt
├── fonts/                  # UI 用フォント（任意）
├── src/
│   ├── api_server.py       # FastAPI（ポート 8765）
│   ├── config.py
│   ├── core.py             # ログ・ファイル情報
│   ├── database.py
│   ├── event_grouper.py    # イベントグルーピング（将来拡張用）
│   ├── services/           # スキャン・解析
│   └── utils.py
└── tests/                  # unittest
```

## テスト

```bash
python tests/run_tests.py
```

## トラブルシューティング

| 現象 | 確認 |
|------|------|
| UI がデータを読めない | API が `127.0.0.1:8765` で起動しているか |
| AI / HF が動かない | `torch` / `transformers`、上記 **AI** 節、`HF_OFFLINE_MODE` 等 |
| `Model not found in cache` | オンラインで一度モデルを取得するか、キャッシュをコピー |
| 遅い | `LOW_LOAD_MODE`、DB の整理、解析対象枚数 |

## 更新履歴（要約）

**v2.3** — `src/` への集約、起動・DB 最適化、差分スキャン（`path_under_root`）、ログローテーション、`src/utils` 分離、動画サムネイル、テスト拡充、Tauri + FastAPI 構成への移行 など。

**v2.2** — イベント系スマート整理、AI ラベリング、極小ファイル削除、セキュリティ・型ヒント強化 など。

**v2.1** — エラーハンドリング、ドキュメント、リソース管理の改善。

## ライセンス

[LICENSE](LICENSE)（MIT）

## 謝辞

OpenCV、Pillow、scikit-learn、CLIP / Hugging Face エコシステムを利用しています。

# PhotoSortX（v3.0）

AI を併用できる画像整理・管理用デスクトップアプリです。Tauri + React 製の UI と、
既存資産を再利用した FastAPI バックエンド（`src/`）で構成されます。フォルダ同期、解析、
重複・ピンボケ・類似の整理、手動仕分け、スマート整理（イベントグルーピング）などをまとめて扱えます。

## 主な機能

| 区分 | 内容 |
|------|------|
| メイン | フォルダ同期（Scan）、詳細解析（Analyze）、ギャラリー、取込前処理 |
| クリーンアップ | 重複（MD5）、ピンボケ（Laplacian）、類似（pHash + VP-Tree）、極小ファイル削除、空フォルダ削除 |
| 整理 | 手動仕分け、スマート整理（イベントグルーピング）、トリアージ、削除済み一覧 |

## 対応フォーマット

対応拡張子は**固定リストではなく、起動時にこの環境の Pillow が実際に開ける形式だけ**を
採用します（宣言だけして開けない形式があると、取り込み後の解析で必ず失敗するため）。
実際のリストはアプリの Settings 画面、または `GET /api/settings` で確認できます。

| 区分 | 形式 |
|------|------|
| 画像（標準） | JPEG (`.jpg .jpeg .jpe .jfif`)、PNG (`.png .apng`)、WebP、TIFF、BMP/DIB、GIF、JPEG 2000 (`.jp2 .j2k .jpf .jpx`)、PSD、TGA、PCX、PPM 系、SGI、QOI |
| 画像（要プラグイン） | HEIC/HEIF (`.heic .heif .hif`) — `pillow-heif` が必要。AVIF (`.avif .avifs`) — Pillow 12 以降で標準対応 |
| 動画 | `.mp4 .mov .m4v .avi .mkv .wmv .webm .mpg .mpeg .ts .m2t .mts .m2ts .3gp .3g2 .vob .asf .flv`（OpenCV の FFMPEG バックエンド） |

意図的に対象外にしているもの: ベクタ/文書（`.eps .ps .wmf .emf`）、科学データ
（`.fits .grib .hdf`）、アイコン/テクスチャ（`.ico .icns .dds`）。写真整理の対象ではなく、
ライブラリを汚すためです。

> **RAW（`.cr2 .nef .arw .dng` など）は未対応です。** Pillow では復号できず、
> `rawpy`（LibRaw）等のデコーダ追加が必要になります。

> `.ts` は TypeScript のソースと拡張子が衝突しますが、本アプリはメディア整理が
> 目的のため MPEG-TS（録画ファイル）として扱います。

候補の定義と判定は `src/image_formats.py` にまとまっています。

## 要件

- **Python 3.10 以上**（`pyproject.toml` の `requires-python` に準拠）
- Windows を主対象にしています
- Rust ツールチェイン（`rustup`）と Node.js（デスクトップアプリのビルド・起動に必要）
- AI（スマート整理の内容ベース分類）は現状 API サーバー側では未対応です（後述）

## セットアップ

```bash
git clone <repository-url>
cd ImageOrganizeForWork

# 1. Python 側（リポジトリ直下）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. フロントエンド
cd app
npm install
```

### AI（任意・将来対応）

`requirements.txt` には含めていません（コアのみ軽量化）。`torch` / `transformers` を
使う機能（CLIP ベースの内容分類）は現状 API サーバー経由では呼び出せません
（[AI_SETUP_GUIDE.md](AI_SETUP_GUIDE.md) 参照、`src/services/organize_service.py` の
`capabilities()` で `content` / `hybrid` は常に `False` を返します）。

## デスクトップアプリ（Tauri + React 版）

`app/` にある UI です。FastAPI（`src/api_server.py`）経由で SQLite（`photos.db`）を扱います。

### 構成

```
PhotoSortX.exe (Tauri)
  └─ 起動時に .venv の python で uvicorn を子プロセス起動（127.0.0.1:8765）
       └─ アプリ終了時に自動で停止
```

`:8765` で既にサーバーが応答している場合は**二重起動せず、それを使います**。

### 日常の起動

インストール済みなら、スタートメニューの **PhotoSortX** から起動します。
バックエンドの起動・停止は不要です（アプリが面倒を見ます）。

開発中は次で起動します。

```bash
cd app
npm run tauri dev
```

### ビルド（インストーラ作成）

```bash
cd app
npm run tauri build
```

`app/src-tauri/target/release/bundle/` に `.msi` / `.exe` が出力されます。

> **リポジトリの場所は固定してください。** 実行ファイルは Python バックエンドを
> 同梱していません。リポジトリ直下の `.venv` と `src/` を参照して動きます。
> リポジトリを移動した場合は、環境変数 `PHOTOSORTX_ROOT` に新しいパスを設定するか、
> 再ビルドしてください。

### バックエンドを更新したとき

`src/` の Python を変更したら、**残っている uvicorn を止めてから**アプリを起動し直して
ください。生きているサーバーがあるとアプリはそれを再利用するため、古いコードが
そのまま使われ続けます。

```bash
# 8765 を掴んでいるプロセスを確認して停止
netstat -ano | findstr 8765
taskkill /PID <PID> /F
```

### トラブルシューティング（Tauri 版）

| 現象 | 確認 |
|------|------|
| 起動画面が「バックエンドが応答しません」のまま | `.venv` の有無、`requirements.txt` の導入、ポート 8765 の競合 |
| 変更したはずの API 挙動が古い | 上記「バックエンドを更新したとき」。古い uvicorn が生き残っている |
| フォルダ一覧に無関係なフォルダが出る | 現在の `root_path` 配下だけが対象。Home で対象フォルダを選び直して Scan |

## ログ

`src/config.py` の `LOG_LEVEL`（既定は `DEBUG`）と `LOG_FILE`（既定 `debug.log`）で制御します。ローテーション付きファイル出力とコンソール出力を使い分けます。本番利用時は `INFO` などへの変更を推奨します。

## 設定・データ

- 設定の定数・既定値: `src/config.py` の `AppConfig`（インスタンス `config`）
- SQLite: 既定でカレントディレクトリの `photos.db`（`config.DB_NAME`）

## プロジェクト構成（抜粋）

```
ImageOrganizeForWork/
├── pyproject.toml          # メタデータ・任意依存 ai・ビルド設定
├── requirements.txt        # コア依存のみ
├── app/                     # Tauri + React 製デスクトップアプリ
│   ├── src-tauri/           # Rust シェル（Python バックエンドの起動・停止）
│   └── src/                 # React UI（pages / components / hooks）
├── src/
│   ├── api_server.py        # FastAPI バックエンド
│   ├── config.py
│   ├── database.py
│   ├── event_grouper.py     # イベントベースのグルーピング（Qt 非依存）
│   ├── image_formats.py
│   ├── utils.py
│   └── services/             # スキャン・解析・重複・整理などのサービス層
└── tests/                   # unittest（python tests/run_tests.py）
```

## テスト

```bash
python tests/run_tests.py
```

（`pytest` 未導入でも上記で全テストを実行できます。）

## トラブルシューティング（要約）

| 現象 | 確認 |
|------|------|
| スマート整理で内容ベース分類が選べない | 現状 API サーバー経由では未対応（[AI_SETUP_GUIDE.md](AI_SETUP_GUIDE.md) 参照）。時間ベースのグルーピングのみ利用可能 |
| 遅い | `LOW_LOAD_MODE`、DB の整理、不要データの削減 |

## ライセンス・履歴

- ライセンス: [LICENSE](LICENSE)（MIT）
- 更新履歴: [CHANGELOG.md](CHANGELOG.md)

## 謝辞

Tauri、React、FastAPI、OpenCV、Pillow、scikit-learn エコシステムを利用しています。

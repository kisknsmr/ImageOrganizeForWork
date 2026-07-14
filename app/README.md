# PhotoSortX Tauri UI（v3）

PhotoSortX の Tauri + React + TypeScript 製フロントエンドです。既存の Python コア（`src/`）を FastAPI（`src/api_server.py`、ポート 8765）でラップし、この UI から呼び出します。

## 起動方法

### 1. バックエンド（FastAPI）

プロジェクトルートで:

```bash
# 依存導入（初回のみ）
.venv\Scripts\pip install -e ".[api]"

# サーバー起動
.venv\Scripts\python -m uvicorn src.api_server:app --host 127.0.0.1 --port 8765
```

※ Tauri デスクトップ版はサイドカーとしてバックエンドを自動起動します。ブラウザ開発時のみ手動起動が必要です。

### 2. フロントエンド

```bash
cd app
npm install
npm run dev        # ブラウザ開発 (http://localhost:1420)
npm run tauri dev  # Tauri デスクトップ開発
npm run build      # 型チェック + プロダクションビルド
npx eslint src     # リント
```

## 画面構成

| ルート | ページ | 内容 |
|--------|--------|------|
| `/import` | Import & Analyze | フォルダ同期（Scan）と詳細解析（Analyze）、進捗表示 |
| `/` | Home | ライブラリ統計・ジョブ進捗 |
| `/gallery` | Gallery | ライブラリ一覧（グリッド/リスト表示） |
| `/triage` | Triage | Keep / Discard / Skip の高速判定 |
| `/duplicates` | Duplicates | MD5（+完全ハッシュ）による重複検出・整理 |
| `/blurry` | Blurry photos | Laplacian によるピンボケ検出 |
| `/tiny` | Tiny files | 極小ファイルの検出・削除 |
| `/similar` | Similar groups | pHash による類似グループ整理（代表ショット提示） |
| `/manual` | Manual sort | フォルダへの手動仕分け（ドラッグ&ドロップ対応） |
| `/ai-organize` | Smart organize | 撮影時刻ベースのイベントグルーピング → フォルダ一括整理 |
| `/cleanup` | Clean up summary | カテゴリ別の集計 |
| `/trash` | Trash | 削除済み一覧・復元・完全削除（退避期間ガードあり） |
| `/settings` | Settings | ライブラリ情報・ゴミ箱フォルダ設定 |

## Smart organize について

- 撮影時刻（mtime）の間隔からイベントを推定し、`整理先/<イベント名>` フォルダへ一括移動します。
- グループ名は適用前に編集できます。日付不明グループは既定で除外されます。
- CLIP による内容ベース分類は AI 依存（`pip install -e ".[ai]"`）+ デスクトップ版（PyQt）でのみ利用できます。API 側の対応状況は `GET /api/organize/capabilities` で確認できます。

## 構成

```
app/
├── src/
│   ├── api/client.ts      # FastAPI クライアント（全エンドポイントのラッパー）
│   ├── components/        # Sidebar / Toast / QueryState など共通部品
│   ├── hooks/             # useViewMode / useDraggableFiles
│   ├── pages/             # 各画面（上表参照）
│   └── types.ts           # API レスポンスの型定義
└── src-tauri/             # Tauri シェル（バックエンドのサイドカー起動を含む）
```

# 更新履歴

## v3.0（開発中: feature/tauri-ui）

- Tauri + React + TypeScript 製の新 UI（`app/`）と FastAPI バックエンド（`src/api_server.py`）を追加
- Import / Gallery / Triage / Duplicates / Blurry / Tiny / Similar / Manual / Trash / Settings の各画面を API 連携で実装
- スマート整理（Smart organize）を新 UI に移植: 撮影時刻ベースのイベントグルーピング → グループ名編集 → フォルダ一括整理（`/api/organize/*`）
- `pyproject.toml` にエクストラ依存を追加（`api`: fastapi/uvicorn、`dev`: httpx）
- organize サービス・API の自動テストを追加（計 108 テスト）
- 前処理画面に空フォルダ一括削除を追加（連なった空フォルダは階層に関係なくまとめて削除）
- **旧 PyQt6 版（`main.py` / `gui/` / `modules/`）を撤去。** 新 UI に移行済み。
  `modules/event_grouper.py`（Qt 非依存）は `src/event_grouper.py` へ移設して存続。
  `modules/ai_classifier.py`（CLIP、QThread 依存）は API サーバーから未使用のため削除 ——
  内容ベースのスマート整理は今後 Qt 非依存の形で再実装が必要
  （`src/services/organize_service.py` の `capabilities()` が常に `content: False` を返すのはこのため）

## v2.3

- プロジェクト構造の整理（`src/` パッケージに config / database / core を集約）
- 起動パフォーマンス大幅改善（PyTorch の遅延ロード化、DB PRAGMA 最適化）
- 差分スキャンのバグ修正（`path_under_root` による誤削除防止）
- 別フォルダ選択時のライブラリ自動置き換え（冗長キャッシュ防止）
- 同一フォルダ判定の強化（実パス解決 + normcase）
- ログローテーション導入（RotatingFileHandler、最大 5MB × 3 世代）
- 軽量ユーティリティを `src/utils.py` に分離（テスト高速化）
- `.gitignore` / `pyproject.toml` / `LICENSE` 追加
- 自動グルーピング機能を削除（類似整理機能で代替可能）
- スマート整理機能の改善（カスタムカテゴリ学習、信頼度スコア表示）
- エラーハンドリングの改善（より詳細なエラーメッセージ）
- 動画サムネイル対応（先頭フレーム抽出）
- テストカバレッジ拡充

## v2.2

- イベントベースのスマート整理機能を追加
- AI によるイベントラベリング機能を追加
- 小さいファイル削除機能を追加
- エラーハンドリングの改善
- 型ヒントの追加
- ドキュメントの充実
- セキュリティの強化（パス検証）
- リソース管理の改善

## v2.1

- エラーハンドリングの改善
- 型ヒントの追加
- ドキュメントの充実
- セキュリティの強化
- リソース管理の改善

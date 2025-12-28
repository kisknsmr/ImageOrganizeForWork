# AI機能セットアップガイド（中国国内向け）

## Hugging Face接続エラー対策

中国国内では、Hugging Faceへの直接アクセスが制限されている場合があります。以下の方法で解決できます。

### 方法1: オフラインモード（推奨）

既にモデルがダウンロード済みの場合、オフラインモードを使用します。

#### 手順

1. **モデルを事前にダウンロード**
   - インターネット接続がある環境（VPN使用など）で一度アプリを起動
   - AI機能を使用してモデルを自動ダウンロード
   - モデルは `~/.cache/huggingface/` に保存されます

2. **config.pyを編集**
   ```python
   # AIモデル設定
   HF_OFFLINE_MODE: bool = True  # オフラインモードを有効化
   ```

3. **アプリを再起動**
   - オフラインモードで動作します

### 方法2: ミラーサイトの使用

中国国内のミラーサイトを使用します。

#### 手順

1. **config.pyを編集**
   ```python
   # AIモデル設定
   HF_MIRROR_SITE: str = "https://hf-mirror.com"  # ミラーサイトURL
   ```

2. **アプリを再起動**
   - ミラーサイトからモデルをダウンロードします

### 方法3: カスタムキャッシュディレクトリ

モデルを特定の場所に保存する場合。

#### 手順

1. **config.pyを編集**
   ```python
   # AIモデル設定
   HF_MODEL_CACHE_DIR: str = "C:/models/huggingface"  # カスタムパス
   ```

2. **アプリを再起動**

### 方法4: プロキシ設定

環境変数でプロキシを設定します。

#### Windows (PowerShell)
```powershell
$env:HTTP_PROXY = "http://proxy.example.com:8080"
$env:HTTPS_PROXY = "http://proxy.example.com:8080"
```

#### Linux/Mac
```bash
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

## モデルの手動ダウンロード

インターネット接続がある環境で、以下のコマンドでモデルを手動ダウンロードできます：

```python
from transformers import CLIPProcessor, CLIPModel

# モデルをダウンロード
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
```

ダウンロード後、`config.py`で`HF_OFFLINE_MODE = True`に設定してください。

## トラブルシューティング

### エラー: "Connection to huggingface.co timed out"

**解決方法**:
1. オフラインモードを有効化（`HF_OFFLINE_MODE = True`）
2. ミラーサイトを使用（`HF_MIRROR_SITE = "https://hf-mirror.com"`）
3. プロキシを設定

### エラー: "Model not found in cache"

**原因**: モデルがダウンロードされていない

**解決方法**:
1. インターネット接続がある環境で一度モデルをダウンロード
2. モデルファイルを手動でコピー
3. オフラインモードを有効化

### エラー: "CUDA out of memory"

**原因**: GPUメモリ不足

**解決方法**:
1. バッチサイズを小さくする（`config.BATCH_SIZE_CLUSTERING = 16`）
2. 処理枚数を減らす
3. CPUモードで実行（GPUを無効化）


import os
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# トップレベルではインポートしない (起動高速化のため)
AI_AVAILABLE = True


class AIWorker(QThread):
    # シグナル定義
    model_loaded = pyqtSignal(bool)
    suggestion_ready = pyqtSignal(list)

    # ★追加: クラスタリング用シグナル (パスリスト, 特徴量テンソル)
    features_ready = pyqtSignal(list, object)

    def __init__(self):
        super().__init__()
        self.ready = False
        self.fns = []  # フォルダパスのリスト（Sorter用）
        self.feats = None  # フォルダのテキスト特徴量（Sorter用）

        # 遅延ロードされるライブラリ類
        self.torch = None
        self.Image = None
        self.proc = None
        self.mod = None

        print("AIWorker: Initialized (Lazy loading mode)", flush=True)

    def run(self):
        """スレッド開始時にAIモデルをロードする"""
        print("AIWorker: Thread Started. Step 0: Imports", flush=True)
        try:
            print("AIWorker: Importing torch...", flush=True)
            import torch

            print("AIWorker: Importing PIL...", flush=True)
            from PIL import Image

            print("AIWorker: Importing transformers...", flush=True)
            from transformers import CLIPProcessor, CLIPModel

            print("AIWorker: Imports done. Assigning...", flush=True)
            self.torch = torch
            self.Image = Image

            print("AIWorker: Loading CLIPProcessor (This is heavy)...", flush=True)
            self.proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

            print("AIWorker: Loading CLIPModel (This is also heavy)...", flush=True)
            self.mod = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")

            print("AIWorker: Model Loaded Successfully!", flush=True)
            self.ready = True
            self.model_loaded.emit(True)

        except ImportError as e:
            print(f"AIWorker: Library missing: {e}", flush=True)
            self.model_loaded.emit(False)
        except Exception as e:
            print(f"AIWorker: CRASHED during load: {e}", flush=True)
            logger.error(f"AI Model Load Error: {e}")
            self.model_loaded.emit(False)

    def set_target_folders(self, paths):
        """
        Sorter機能用: フォルダ名をAIに学習(ベクトル化)させる
        """
        if not self.ready or not paths:
            print("AIWorker: Not ready or no paths for set_target_folders", flush=True)
            return

        self.fns = paths
        labels = [os.path.basename(p) for p in paths]
        try:
            print(f"AIWorker: Vectorizing {len(labels)} folder names...", flush=True)
            inp = self.proc(text=labels, return_tensors="pt", padding=True)

            with self.torch.no_grad():
                self.feats = self.mod.get_text_features(**inp)
                self.feats /= self.feats.norm(dim=-1, keepdim=True)

            print("AIWorker: Folder vectorization complete.", flush=True)
        except Exception as e:
            print(f"AIWorker: Folder Vectorization Error {e}", flush=True)

    def predict(self, path):
        """
        Sorter機能用: 画像のパスを受け取り、最も近いフォルダを推論する
        """
        if not self.ready or not self.fns:
            print("AIWorker: Predict skipped (Not ready or no folders set)", flush=True)
            return

        try:
            print(f"AIWorker: Predicting for {os.path.basename(path)}", flush=True)
            image = self.Image.open(path)
            inp = self.proc(images=image, return_tensors="pt")

            with self.torch.no_grad():
                img_f = self.mod.get_image_features(**inp)
                img_f /= img_f.norm(dim=-1, keepdim=True)

                # 類似度計算 (画像 vs フォルダテキスト)
                sim = (100.0 * img_f @ self.feats.T).softmax(dim=-1)
                values, indices = sim[0].topk(3)

            sugs = [(values[j].item(), self.fns[indices[j]]) for j in range(len(values))]
            print(f"AIWorker: Suggestion -> {sugs[0][1]} ({sugs[0][0]:.2f})", flush=True)
            self.suggestion_ready.emit(sugs)

        except Exception as e:
            print(f"AIWorker: Prediction Error {e}", flush=True)

    # ★追加機能: クラスタリング画面(ClusteringPage)用
    def vectorize_images(self, paths):
        """
        指定された画像リストを一括でベクトル化し、features_readyシグナルで返す
        """
        if not self.ready:
            print("AIWorker: vectorize_images called but AI is NOT READY.", flush=True)
            self.features_ready.emit(paths, None)
            return

        print(f"AIWorker: Start vectorizing {len(paths)} images for clustering...", flush=True)

        valid_paths = []
        valid_images = []

        # 1. 画像読み込み
        for p in paths:
            try:
                img = self.Image.open(p).convert('RGB')
                valid_images.append(img)
                valid_paths.append(p)
            except Exception as e:
                print(f"AIWorker: Skip invalid image {os.path.basename(p)}: {e}", flush=True)

        if not valid_images:
            print("AIWorker: No valid images to process.", flush=True)
            self.features_ready.emit([], None)
            return

        # 2. バッチ処理で特徴抽出
        # メモリ溢れ防止のため、少しずつ処理する（例: 32枚ずつ）
        batch_size = 32
        all_features = []

        try:
            total = len(valid_images)
            print(f"AIWorker: Processing {total} images in batches of {batch_size}...", flush=True)

            for i in range(0, total, batch_size):
                batch_imgs = valid_images[i: i + batch_size]
                print(f"AIWorker: Processing batch {i} to {i + len(batch_imgs)}...", flush=True)

                inputs = self.proc(images=batch_imgs, return_tensors="pt", padding=True)

                with self.torch.no_grad():
                    img_features = self.mod.get_image_features(**inputs)
                    # 正規化 (これをしないとコサイン類似度が正しく計算できない)
                    img_features /= img_features.norm(dim=-1, keepdim=True)
                    all_features.append(img_features)

            # 3. 全バッチを結合
            print("AIWorker: Concatenating features...", flush=True)
            final_tensor = self.torch.cat(all_features, dim=0)

            print(f"AIWorker: Vectorization Done. Shape: {final_tensor.shape}", flush=True)
            self.features_ready.emit(valid_paths, final_tensor)

        except Exception as e:
            print(f"AIWorker: Vectorization CRASHED: {e}", flush=True)
            self.features_ready.emit(valid_paths, None)
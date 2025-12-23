import os
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# トップレベルではインポートしない
AI_AVAILABLE = True


class AIWorker(QThread):
    model_loaded = pyqtSignal(bool)
    suggestion_ready = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.ready = False
        self.fns = []
        self.torch = None
        self.Image = None
        self.proc = None
        self.mod = None

    def run(self):
        print("AI Worker: Thread Started. Step 0: Imports", flush=True)
        try:
            print("AI Worker: Importing torch...", flush=True)
            import torch

            print("AI Worker: Importing PIL...", flush=True)
            from PIL import Image

            print("AI Worker: Importing transformers...", flush=True)
            from transformers import CLIPProcessor, CLIPModel

            print("AI Worker: Imports done. Assigning...", flush=True)
            self.torch = torch
            self.Image = Image

            print("AI Worker: Loading CLIPProcessor (This is heavy)...", flush=True)
            self.proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

            print("AI Worker: Loading CLIPModel (This is also heavy)...", flush=True)
            self.mod = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")

            print("AI Worker: Model Loaded Successfully!", flush=True)
            self.ready = True
            self.model_loaded.emit(True)

        except ImportError as e:
            print(f"AI Worker: Library missing: {e}", flush=True)
            self.model_loaded.emit(False)
        except Exception as e:
            print(f"AI Worker: CRASHED during load: {e}", flush=True)
            logger.error(f"AI Model Load Error: {e}")
            self.model_loaded.emit(False)

    def set_target_folders(self, paths):
        """フォルダ名をAIに学習(ベクトル化)させる"""
        if not self.ready or not paths: return
        self.fns = paths
        labels = [os.path.basename(p) for p in paths]
        try:
            print(f"AI Worker: Vectorizing {len(labels)} folders...", flush=True)
            inp = self.proc(text=labels, return_tensors="pt", padding=True)
            with self.torch.no_grad():
                self.feats = self.mod.get_text_features(**inp)
                self.feats /= self.feats.norm(dim=-1, keepdim=True)
            print("AI Worker: Vectorization complete.", flush=True)
        except Exception as e:
            print(f"AI Worker: Vectorization Error {e}", flush=True)

    def predict(self, path):
        """画像のパスを受け取り、最も近いフォルダを推論する"""
        if not self.ready or not self.fns: return
        try:
            image = self.Image.open(path)
            inp = self.proc(images=image, return_tensors="pt")

            with self.torch.no_grad():
                img_f = self.mod.get_image_features(**inp)
                img_f /= img_f.norm(dim=-1, keepdim=True)
                sim = (100.0 * img_f @ self.feats.T).softmax(dim=-1)
                values, indices = sim[0].topk(3)

            sugs = [(values[j].item(), self.fns[indices[j]]) for j in range(len(values))]
            self.suggestion_ready.emit(sugs)

        except Exception as e:
            print(f"AI Worker: Prediction Error {e}", flush=True)
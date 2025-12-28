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
        self.run_flag = True  # 停止フラグ

        # 遅延ロードされるライブラリ類
        self.torch = None
        self.Image = None
        self.proc = None
        self.mod = None

        print("AIWorker: Initialized (Lazy loading mode) - Preloading libraries on Main Thread...", flush=True)
        self._preload_libraries()
    
    def _preload_libraries(self):
        """
        Windowsでのクラッシュ(STATUS_STACK_BUFFER_OVERRUN)を防ぐため、
        重いライブラリのインポートはメインスレッドで行う
        """
        try:
            print("AIWorker: Importing torch...", flush=True)
            import torch
            self.torch = torch

            print("AIWorker: Importing PIL...", flush=True)
            from PIL import Image
            self.Image = Image

            print("AIWorker: Importing transformers...", flush=True)
            try:
                from transformers import CLIPProcessor, CLIPModel
            except Exception as e_tf:
                print(f"AIWorker: CRITICAL - Failed to import transformers: {e_tf}", flush=True)
                logger.error(f"Transformers import failed: {e_tf}", exc_info=True)
                return

            import os
            
            # 設定をインポート
            from config import config
            
            # Hugging Face接続エラー対策
            model_name = config.CLIP_MODEL_NAME
            load_kwargs = {}
            
            # オフラインモード設定
            if config.HF_OFFLINE_MODE:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                load_kwargs["local_files_only"] = True
                print("AIWorker: Using offline mode (local files only)", flush=True)
            
            # ミラーサイト設定
            if config.HF_MIRROR_SITE:
                os.environ["HF_ENDPOINT"] = config.HF_MIRROR_SITE
                print(f"AIWorker: Using mirror site: {config.HF_MIRROR_SITE}", flush=True)
            
            # キャッシュディレクトリ設定
            if config.HF_MODEL_CACHE_DIR:
                cache_dir = config.HF_MODEL_CACHE_DIR
                os.makedirs(cache_dir, exist_ok=True)
                load_kwargs["cache_dir"] = cache_dir
                print(f"AIWorker: Using cache directory: {cache_dir}", flush=True)

            print("AIWorker: Loading CLIPProcessor (This is heavy)...", flush=True)
            
            # 1. Try Offline (Processor)
            try:
                self.proc = CLIPProcessor.from_pretrained(model_name, local_files_only=True, **load_kwargs)
                print("AIWorker: CLIPProcessor loaded from local cache.", flush=True)
            except Exception as e_local:
                if config.HF_OFFLINE_MODE:
                    print(f"AIWorker: Failed to load Processor locally and Offline Mode is ON: {e_local}", flush=True)
                    raise e_local
                
                print(f"AIWorker: Local load failed, trying online... ({e_local})", flush=True)
                # 2. Try Online (Processor)
                try:
                    self.proc = CLIPProcessor.from_pretrained(model_name, **load_kwargs)
                except Exception as e_online:
                    logger.error(f"Failed to load CLIPProcessor (Online): {e_online}", exc_info=True)
                    raise e_online

            print("AIWorker: Loading CLIPModel (This is also heavy)...", flush=True)
            # 1. Try Offline (Model)
            try:
                self.mod = CLIPModel.from_pretrained(model_name, local_files_only=True, **load_kwargs)
                print("AIWorker: CLIPModel loaded from local cache.", flush=True)
            except Exception as e_local:
                if config.HF_OFFLINE_MODE:
                    print(f"AIWorker: Failed to load Model locally and Offline Mode is ON: {e_local}", flush=True)
                    raise e_local
                
                print(f"AIWorker: Local load failed, trying online... ({e_local})", flush=True)
                # 2. Try Online (Model)
                try:
                    self.mod = CLIPModel.from_pretrained(model_name, **load_kwargs)
                except Exception as e_online:
                    logger.error(f"Failed to load CLIPModel (Online): {e_online}", exc_info=True)
                    raise e_online

            print("AIWorker: Model Loaded Successfully!", flush=True)
            self.ready = True
            
        except ImportError as e:
            print(f"AIWorker: Library missing: {e}", flush=True)
            logger.error(f"AI Library Import Error: {e}")
        except Exception as e:
            print(f"AIWorker: CRASHED during load: {e}", flush=True)
            logger.error(f"AI Model Load Error: {e}", exc_info=True)

    def stop(self):
        """処理を停止"""
        self.run_flag = False
        print("AIWorker: Stop requested", flush=True)
    
    def reset_stop_flag(self):
        """停止フラグをリセット（新しい処理開始時）"""
        self.run_flag = True

    def run(self):
        """
        スレッド本体。今は軽い処理のみ。
        """
        if self.ready:
            self.model_loaded.emit(True)
        else:
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

        # 停止フラグをリセット
        self.reset_stop_flag()
        
        print(f"AIWorker: Start vectorizing {len(paths)} images for clustering...", flush=True)

        valid_paths = []
        valid_images = []

        # 1. 画像読み込み
        for p in paths:
            if not self.run_flag:
                print("AIWorker: Image loading stopped by user", flush=True)
                self.features_ready.emit(valid_paths, None)
                return
            
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
        from config import config
        batch_size = config.BATCH_SIZE_CLUSTERING
        all_features = []

        try:
            total = len(valid_images)
            print(f"AIWorker: Processing {total} images in batches of {batch_size}...", flush=True)

            for i in range(0, total, batch_size):
                if not self.run_flag:
                    print("AIWorker: Processing stopped by user", flush=True)
                    self.features_ready.emit(valid_paths[:i], None)
                    return
                
                batch_imgs = valid_images[i: i + batch_size]
                print(f"AIWorker: Processing batch {i} to {i + len(batch_imgs)}...", flush=True)

                inputs = self.proc(images=batch_imgs, return_tensors="pt", padding=True)

                with self.torch.no_grad():
                    img_features = self.mod.get_image_features(**inputs)
                    # 正規化 (これをしないとコサイン類似度が正しく計算できない)
                    img_features /= img_features.norm(dim=-1, keepdim=True)
                    all_features.append(img_features)

            if not self.run_flag:
                print("AIWorker: Processing stopped by user", flush=True)
                self.features_ready.emit(valid_paths[:len(all_features) * batch_size], None)
                return

            # 3. 全バッチを結合
            print("AIWorker: Concatenating features...", flush=True)
            final_tensor = self.torch.cat(all_features, dim=0)

            print(f"AIWorker: Vectorization Done. Shape: {final_tensor.shape}", flush=True)
            self.features_ready.emit(valid_paths, final_tensor)
            
        except Exception as e:
            print(f"AIWorker: Vectorization CRASHED: {e}", flush=True)
            logger.error(f"Vectorization error: {e}", exc_info=True)
            self.features_ready.emit(valid_paths, None)

    # ★追加機能: イベントラベリング用
    def predict_event(self, image_paths, top_k=5):
        """
        イベント（画像のグループ）の代表的なラベルを推論する
        Args:
            image_paths: イベントに含まれる画像パスのリスト
            top_k: 判断に使用する画像の最大枚数（多すぎると遅いので間引く）
        Returns:
            suggested_label (str): 推論されたラベル (例: "ゴルフ", "食事", "旅行")
        """
        if not self.ready:
            return None
            
        # 判定用ラベル（コンテキスト重視）
        EVENT_LABELS = [
            "ゴルフ", "バスケットボール", "野球", "サッカー", "テニス",
            "仕事_書類", "スクリーンショット", 
            "食事_居酒屋", "カフェ_スイーツ", "ラーメン",
            "旅行_風景", "海_ビーチ", "山_自然", "神社_寺",
            "街並み", "乗り物", "猫_ペット", "犬_ペット",
            "集合写真", "屋内_部屋", "日常"
        ]
        
        try:
            # ラベルのベクトル化（キャッシュしても良いが、ここでは都度計算）
            text_inputs = self.proc(text=EVENT_LABELS, return_tensors="pt", padding=True)
            with self.torch.no_grad():
                text_feats = self.mod.get_text_features(**text_inputs)
                text_feats /= text_feats.norm(dim=-1, keepdim=True)

            # 画像の選定（ランダムではなく、均等に分散させる）
            if len(image_paths) > top_k:
                step = len(image_paths) // top_k
                selected_paths = [image_paths[i] for i in range(0, len(image_paths), step)][:top_k]
            else:
                selected_paths = image_paths

            valid_images = []
            for p in selected_paths:
                # Video file skip check
                ext = os.path.splitext(p)[1].lower()
                if ext in ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm']:
                    print(f"AIWorker: Skipping video file {os.path.basename(p)}", flush=True)
                    continue

                try:
                    img = self.Image.open(p).convert('RGB')
                    valid_images.append(img)
                except:
                    continue
            
            if not valid_images:
                return None

            # 画像のベクトル化
            img_inputs = self.proc(images=valid_images, return_tensors="pt", padding=True)
            with self.torch.no_grad():
                img_feats = self.mod.get_image_features(**img_inputs)
                img_feats /= img_feats.norm(dim=-1, keepdim=True)
            
            # 類似度計算: (画像数 x ラベル数)
            sim_matrix = (100.0 * img_feats @ text_feats.T).softmax(dim=-1)
            
            # 平均スコアを取る
            avg_scores = sim_matrix.mean(dim=0) # (ラベル数, )
            
            best_idx = avg_scores.argmax().item()
            best_score = avg_scores[best_idx].item()
            
            label = EVENT_LABELS[best_idx]
            print(f"AIWorker: Event Prediction -> {label} (Score: {best_score:.2f})", flush=True)
            
            # スコアが低すぎる場合は「その他」扱いでも良いが、一旦返す
            return label

        except Exception as e:
            print(f"AIWorker: Event Prediction Error {e}", flush=True)
            return None
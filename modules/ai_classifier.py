import os
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# ログ出力ヘルパー関数（print文の置き換え用）
def log_info(message: str):
    """INFOレベルのログを出力（print文の置き換え用）"""
    logger.info(message)

def log_debug(message: str):
    """DEBUGレベルのログを出力（print文の置き換え用）"""
    logger.debug(message)

def log_warning(message: str):
    """WARNINGレベルのログを出力（print文の置き換え用）"""
    logger.warning(message)

def log_error(message: str):
    """ERRORレベルのログを出力（print文の置き換え用）"""
    logger.error(message)

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

        logger.info("AIWorker: Initialized (Lazy loading mode) - Preloading libraries on Main Thread...")
        self._preload_libraries()
    
    def _preload_libraries(self):
        """
        Windowsでのクラッシュ(STATUS_STACK_BUFFER_OVERRUN)を防ぐため、
        重いライブラリのインポートはメインスレッドで行う
        """
        try:
            logger.info("AIWorker: Importing torch...")
            import torch
            self.torch = torch

            logger.info("AIWorker: Importing PIL...")
            from PIL import Image
            self.Image = Image

            logger.info("AIWorker: Importing transformers...")
            try:
                from transformers import CLIPProcessor, CLIPModel
            except Exception as e_tf:
                logger.critical(f"AIWorker: CRITICAL - Failed to import transformers: {e_tf}")
                logger.error(f"Transformers import failed: {e_tf}", exc_info=True)
                return

            import os
            
            # 設定をインポート
            from src.config import config
            
            # Hugging Face接続エラー対策
            model_name = config.CLIP_MODEL_NAME
            load_kwargs = {}
            
            # オフラインモード設定
            if config.HF_OFFLINE_MODE:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                load_kwargs["local_files_only"] = True
                logger.info("AIWorker: Using offline mode (local files only)")
            
            # ミラーサイト設定
            if config.HF_MIRROR_SITE:
                os.environ["HF_ENDPOINT"] = config.HF_MIRROR_SITE
                logger.info(f"AIWorker: Using mirror site: {config.HF_MIRROR_SITE}")
            
            # キャッシュディレクトリ設定
            if config.HF_MODEL_CACHE_DIR:
                cache_dir = config.HF_MODEL_CACHE_DIR
                os.makedirs(cache_dir, exist_ok=True)
                load_kwargs["cache_dir"] = cache_dir
                logger.info(f"AIWorker: Using cache directory: {cache_dir}")

            logger.info("AIWorker: Loading CLIPProcessor (This is heavy)...")
            
            # 1. Try Offline (Processor)
            try:
                self.proc = CLIPProcessor.from_pretrained(model_name, local_files_only=True, **load_kwargs)
                logger.info("AIWorker: CLIPProcessor loaded from local cache.")
            except Exception as e_local:
                if config.HF_OFFLINE_MODE:
                    logger.error(f"AIWorker: Failed to load Processor locally and Offline Mode is ON: {e_local}")
                    raise e_local
                
                logger.warning(f"AIWorker: Local load failed, trying online... ({e_local})")
                # 2. Try Online (Processor)
                try:
                    logger.info("AIWorker: Attempting to download CLIPProcessor from Hugging Face...")
                    self.proc = CLIPProcessor.from_pretrained(model_name, **load_kwargs)
                    logger.info("AIWorker: CLIPProcessor downloaded successfully from Hugging Face.")
                except ConnectionError as e_conn:
                    logger.error(f"AIWorker: Network connection error while loading CLIPProcessor: {e_conn}", exc_info=True)
                    logger.error("AIWorker: Please check your internet connection or use offline mode (HF_OFFLINE_MODE=True)")
                    raise ConnectionError(f"Failed to connect to Hugging Face: {e_conn}") from e_conn
                except TimeoutError as e_timeout:
                    logger.error(f"AIWorker: Timeout error while loading CLIPProcessor: {e_timeout}", exc_info=True)
                    logger.error("AIWorker: Connection to Hugging Face timed out. Please check your network or use offline mode.")
                    raise TimeoutError(f"Connection timeout to Hugging Face: {e_timeout}") from e_timeout
                except Exception as e_online:
                    logger.error(f"AIWorker: Failed to load CLIPProcessor (Online): {e_online}", exc_info=True)
                    logger.error("AIWorker: This may be due to network issues, firewall, or Hugging Face service problems.")
                    raise e_online

            logger.info("AIWorker: Loading CLIPModel (This is also heavy)...")
            # 1. Try Offline (Model)
            try:
                self.mod = CLIPModel.from_pretrained(model_name, local_files_only=True, **load_kwargs)
                logger.info("AIWorker: CLIPModel loaded from local cache.")
            except Exception as e_local:
                if config.HF_OFFLINE_MODE:
                    logger.error(f"AIWorker: Failed to load Model locally and Offline Mode is ON: {e_local}")
                    raise e_local
                
                logger.warning(f"AIWorker: Local load failed, trying online... ({e_local})")
                # 2. Try Online (Model)
                try:
                    logger.info("AIWorker: Attempting to download CLIPModel from Hugging Face...")
                    self.mod = CLIPModel.from_pretrained(model_name, **load_kwargs)
                    logger.info("AIWorker: CLIPModel downloaded successfully from Hugging Face.")
                except ConnectionError as e_conn:
                    logger.error(f"AIWorker: Network connection error while loading CLIPModel: {e_conn}", exc_info=True)
                    logger.error("AIWorker: Please check your internet connection or use offline mode (HF_OFFLINE_MODE=True)")
                    raise ConnectionError(f"Failed to connect to Hugging Face: {e_conn}") from e_conn
                except TimeoutError as e_timeout:
                    logger.error(f"AIWorker: Timeout error while loading CLIPModel: {e_timeout}", exc_info=True)
                    logger.error("AIWorker: Connection to Hugging Face timed out. Please check your network or use offline mode.")
                    raise TimeoutError(f"Connection timeout to Hugging Face: {e_timeout}") from e_timeout
                except Exception as e_online:
                    logger.error(f"AIWorker: Failed to load CLIPModel (Online): {e_online}", exc_info=True)
                    logger.error("AIWorker: This may be due to network issues, firewall, or Hugging Face service problems.")
                    raise e_online

            logger.info("AIWorker: Model Loaded Successfully!")
            self.ready = True
            
        except ImportError as e:
            logger.error(f"AIWorker: Library missing: {e}")
            logger.error(f"AI Library Import Error: {e}")
        except Exception as e:
            logger.critical(f"AIWorker: CRASHED during load: {e}")
            logger.error(f"AI Model Load Error: {e}", exc_info=True)

    def stop(self):
        """処理を停止"""
        self.run_flag = False
        logger.info("AIWorker: Stop requested")
    
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
            logger.warning("AIWorker: Not ready or no paths for set_target_folders")
            return

        self.fns = paths
        labels = [os.path.basename(p) for p in paths]
        try:
            logger.info(f"AIWorker: Vectorizing {len(labels)} folder names...")
            inp = self.proc(text=labels, return_tensors="pt", padding=True)

            with self.torch.no_grad():
                self.feats = self.mod.get_text_features(**inp)
                self.feats /= self.feats.norm(dim=-1, keepdim=True)

            logger.info("AIWorker: Folder vectorization complete.")
        except Exception as e:
            logger.error(f"AIWorker: Folder Vectorization Error {e}", exc_info=True)

    def predict(self, path):
        """
        Sorter機能用: 画像のパスを受け取り、最も近いフォルダを推論する
        """
        if not self.ready or not self.fns:
            logger.warning("AIWorker: Predict skipped (Not ready or no folders set)")
            return

        try:
            logger.debug(f"AIWorker: Predicting for {os.path.basename(path)}")
            image = self.Image.open(path)
            inp = self.proc(images=image, return_tensors="pt")

            with self.torch.no_grad():
                img_f = self.mod.get_image_features(**inp)
                img_f /= img_f.norm(dim=-1, keepdim=True)

                # 類似度計算 (画像 vs フォルダテキスト)
                sim = (100.0 * img_f @ self.feats.T).softmax(dim=-1)
                values, indices = sim[0].topk(3)

            sugs = [(values[j].item(), self.fns[indices[j]]) for j in range(len(values))]
            logger.debug(f"AIWorker: Suggestion -> {sugs[0][1]} ({sugs[0][0]:.2f})")
            self.suggestion_ready.emit(sugs)

        except Exception as e:
            logger.error(f"AIWorker: Prediction Error {e}", exc_info=True)

    def vectorize_images(self, paths):
        """
        指定された画像リストを一括でベクトル化し、features_readyシグナルで返す
        画像の特徴量抽出に使用
        """
        if not self.ready:
            logger.warning("AIWorker: vectorize_images called but AI is NOT READY.")
            self.features_ready.emit(paths, None)
            return

        # 停止フラグをリセット
        self.reset_stop_flag()
        
        logger.info(f"AIWorker: Start vectorizing {len(paths)} images...")

        valid_paths = []
        valid_images = []

        # 1. 画像読み込み
        for p in paths:
            if not self.run_flag:
                logger.info("AIWorker: Image loading stopped by user")
                self.features_ready.emit(valid_paths, None)
                return
            
            try:
                img = self.Image.open(p).convert('RGB')
                valid_images.append(img)
                valid_paths.append(p)
            except Exception as e:
                logger.warning(f"AIWorker: Skip invalid image {os.path.basename(p)}: {e}")

        if not valid_images:
            logger.warning("AIWorker: No valid images to process.")
            self.features_ready.emit([], None)
            return

        # 2. バッチ処理で特徴抽出
        # メモリ溢れ防止のため、少しずつ処理する（例: 32枚ずつ）
        from src.config import config
        batch_size = config.BATCH_SIZE_CLUSTERING
        all_features = []

        try:
            total = len(valid_images)
            logger.info(f"AIWorker: Processing {total} images in batches of {batch_size}...")

            for i in range(0, total, batch_size):
                if not self.run_flag:
                    logger.info("AIWorker: Processing stopped by user")
                    self.features_ready.emit(valid_paths[:i], None)
                    return
                
                batch_imgs = valid_images[i: i + batch_size]
                logger.debug(f"AIWorker: Processing batch {i} to {i + len(batch_imgs)}...")

                inputs = self.proc(images=batch_imgs, return_tensors="pt", padding=True)

                with self.torch.no_grad():
                    img_features = self.mod.get_image_features(**inputs)
                    # 正規化 (これをしないとコサイン類似度が正しく計算できない)
                    img_features /= img_features.norm(dim=-1, keepdim=True)
                    all_features.append(img_features)

            if not self.run_flag:
                logger.info("AIWorker: Processing stopped by user")
                self.features_ready.emit(valid_paths[:len(all_features) * batch_size], None)
                return

            # 3. 全バッチを結合
            logger.debug("AIWorker: Concatenating features...")
            final_tensor = self.torch.cat(all_features, dim=0)

            logger.info(f"AIWorker: Vectorization Done. Shape: {final_tensor.shape}")
            self.features_ready.emit(valid_paths, final_tensor)
            
        except Exception as e:
            logger.critical(f"AIWorker: Vectorization CRASHED: {e}")
            logger.error(f"Vectorization error: {e}", exc_info=True)
            self.features_ready.emit(valid_paths, None)

    # ★追加機能: イベントラベリング用
    def predict_event(self, image_paths, top_k=5, return_top_n=1, min_confidence=None):
        """
        イベント（画像のグループ）の代表的なラベルを推論する
        Args:
            image_paths: イベントに含まれる画像パスのリスト
            top_k: 判断に使用する画像の最大枚数（多すぎると遅いので間引く）
            return_top_n: 返す候補の数（1の場合は最上位のみ、3の場合は上位3候補）
            min_confidence: 信頼度の最小閾値（Noneの場合はconfigから取得）
        Returns:
            return_top_n=1の場合: suggested_label (str) または None（信頼度不足の場合）
            return_top_n>1の場合: [(label, score), ...] のリスト（スコア降順）
        """
        if not self.ready:
            return None
            
        # 判定用ラベル（コンテキスト重視）- 設定ファイルから取得 + カスタムカテゴリ
        from src.config import config
        EVENT_LABELS = list(config.AI_EVENT_LABELS)
        # カスタムカテゴリを追加（データベースから取得）
        # 注意: このメソッドはAIWorker内で呼ばれるため、db_managerへのアクセスが必要
        # 簡易実装: カスタムカテゴリは設定ファイルに統合するか、別の方法で取得
        # 一旦、設定ファイルのみを使用（カスタムカテゴリは次回起動時にconfigに反映される想定）
        
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
                    logger.debug(f"AIWorker: Skipping video file {os.path.basename(p)}")
                    continue

                try:
                    img = self.Image.open(p).convert('RGB')
                    valid_images.append(img)
                except (OSError, IOError) as e:
                    logger.warning(f"Failed to open image for event prediction: {p}, error: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Unexpected error opening image for event prediction: {p}, error: {e}")
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
            
            # 信頼度閾値を取得
            if min_confidence is None:
                from src.config import config
                min_confidence = config.AI_CONFIDENCE_THRESHOLD
            
            # スコアをソートして上位N候補を取得
            sorted_scores, sorted_indices = avg_scores.sort(descending=True)
            
            # 上位N候補を取得
            top_n = min(return_top_n, len(EVENT_LABELS))
            top_candidates = []
            for i in range(top_n):
                idx = sorted_indices[i].item()
                score = sorted_scores[i].item()
                label = EVENT_LABELS[idx]
                top_candidates.append((label, score))
            
            best_label, best_score = top_candidates[0]
            
            # 複数候補を返す場合
            if return_top_n > 1:
                # 信頼度チェック: 最上位候補が閾値未満の場合は空リストを返す
                if best_score < min_confidence:
                    logger.info(f"AIWorker: Event Prediction -> Low confidence ({best_score:.2f} < {min_confidence:.2f}), returning empty list")
                    return []
                logger.info(f"AIWorker: Event Prediction -> Top {top_n} candidates: {top_candidates}")
                return top_candidates
            
            # 単一候補を返す場合（信頼度チェック）
            if best_score >= min_confidence:
                logger.info(f"AIWorker: Event Prediction -> {best_label} (Score: {best_score:.2f})")
                return best_label
            else:
                logger.info(f"AIWorker: Event Prediction -> Low confidence ({best_score:.2f} < {min_confidence:.2f}), returning None")
                return None

        except Exception as e:
            logger.error(f"AIWorker: Event Prediction Error {e}", exc_info=True)
            return None
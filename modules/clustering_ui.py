"""
自動グルーピングUIモジュール
DBSCANクラスタリングを使用して画像を自動的にグループ化
"""
import sys
import os
import shutil
import logging
import numpy as np
from typing import List, Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFileDialog, QFrame, QScrollArea, QProgressBar,
                             QMessageBox, QInputDialog)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

# 設定
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

# インポート確認
try:
    from sklearn.cluster import DBSCAN
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

AI_AVAILABLE = True
logger = logging.getLogger(__name__)


class ClusteringPage(QWidget):
    def __init__(self):
        super().__init__()
        self.ai_worker = None
        self.target_files = []
        self.is_processing = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ヘッダー
        header = QHBoxLayout()
        self.lbl_title = QLabel("🤖 AI 自動グルーピング (DBSCAN Clustering)")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(self.lbl_title)

        self.btn_open = QPushButton(f"📂 フォルダを選択 (最大 {config.MAX_CLUSTERING_IMAGES:,}枚)")
        self.btn_open.clicked.connect(self.select_folder)
        self.btn_open.setStyleSheet("background-color: #007acc; color: white; padding: 8px;")
        header.addWidget(self.btn_open)
        
        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.clicked.connect(self.stop_processing)
        self.btn_stop.setStyleSheet("background-color: #d83b01; color: white; padding: 8px;")
        self.btn_stop.setEnabled(False)
        header.addWidget(self.btn_stop)
        
        layout.addLayout(header)

        self.lbl_status = QLabel("scikit-learn を使用して自動分類します")
        self.lbl_status.setStyleSheet("color: #aaa; margin: 10px 0;")
        layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("height: 4px;")
        layout.addWidget(self.progress)

        # 結果エリア
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)

    def select_folder(self):
        if not SKLEARN_AVAILABLE:
            QMessageBox.critical(self, "エラー",
                                 "scikit-learn がインストールされていません。\npip install scikit-learn を実行してください。")
            return

        folder = QFileDialog.getExistingDirectory(self, "フォルダ選択")
        if not folder: return

        # 画像収集
        exts = ('.jpg', '.jpeg', '.png', '.webp')
        self.target_files = []
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(exts):
                    self.target_files.append(os.path.join(root, f))

        if not self.target_files:
            QMessageBox.information(self, "情報", "画像ファイルが見つかりませんでした")
            return

        # 制限チェック: 超過している場合は処理を停止
        if len(self.target_files) > config.MAX_CLUSTERING_IMAGES:
            reply = QMessageBox.warning(
                self, 
                "枚数制限超過",
                f"選択したフォルダには {len(self.target_files):,} 枚の画像があります。\n\n"
                f"処理速度のため、最大 {config.MAX_CLUSTERING_IMAGES:,} 枚まで処理可能です。\n\n"
                f"最初の {config.MAX_CLUSTERING_IMAGES:,} 枚のみ処理しますか？\n"
                f"（「いいえ」を選択すると処理をキャンセルします）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                self.lbl_status.setText("処理をキャンセルしました")
                return
            
            self.target_files = self.target_files[:config.MAX_CLUSTERING_IMAGES]
            QMessageBox.information(
                self,
                "制限適用",
                f"{config.MAX_CLUSTERING_IMAGES:,} 枚に制限して処理します。\n"
                f"処理時間の目安: 約 {self._estimate_processing_time(len(self.target_files))} 分"
            )

        self.lbl_status.setText(f"{len(self.target_files)} 枚の特徴量を抽出中...")
        self.progress.setRange(0, 0)
        self.is_processing = True
        self.btn_open.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.start_ai_process()
    
    def _estimate_processing_time(self, num_images: int) -> int:
        """
        処理時間を推定（分単位）
        
        Args:
            num_images: 画像枚数
            
        Returns:
            推定処理時間（分）
        """
        # CLIPモデルで1枚あたり約0.2-0.5秒（CPU）、0.05-0.1秒（GPU）
        # バッチ処理（32枚ずつ）を考慮して、平均0.15秒/枚と仮定
        seconds_per_image = 0.15
        total_seconds = num_images * seconds_per_image
        minutes = int(total_seconds / 60) + 1  # 切り上げ
        return minutes

    def start_ai_process(self):
        if self.ai_worker and self.ai_worker.ready:
            # 停止フラグをリセットしてから処理開始
            self.ai_worker.reset_stop_flag()
            self.ai_worker.vectorize_images(self.target_files)
            return

        try:
            from modules.ai_classifier import AIWorker
            if not self.ai_worker:
                self.ai_worker = AIWorker()
                self.ai_worker.model_loaded.connect(self.on_model_loaded)
                self.ai_worker.features_ready.connect(self.on_features_ready)
                self.ai_worker.start()
            else:
                # 既にワーカーが存在する場合は、モデルがロードされるまで待つ
                if self.ai_worker.ready:
                    self.ai_worker.reset_stop_flag()
                    self.ai_worker.vectorize_images(self.target_files)
        except ImportError as e:
            logger.error(f"Failed to import AIWorker: {e}")
            self.lbl_status.setText("AI初期化エラー: ライブラリが見つかりません")
            self._reset_ui()
        except Exception as e:
            logger.error(f"Failed to initialize AI: {e}", exc_info=True)
            self.lbl_status.setText("AI初期化エラー")
            self._reset_ui()
    
    def stop_processing(self):
        """処理を停止"""
        if self.is_processing and self.ai_worker:
            self.ai_worker.stop()
            self.lbl_status.setText("処理を停止中...")
            logger.info("User requested to stop clustering processing")
    
    def _reset_ui(self):
        """UIをリセット（処理完了またはエラー時）"""
        self.is_processing = False
        self.btn_open.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setRange(0, 100)

    def on_model_loaded(self, success):
        if success:
            if self.is_processing and self.target_files:
                self.ai_worker.vectorize_images(self.target_files)
        else:
            self.lbl_status.setText("AIモデルの読み込みに失敗しました")
            QMessageBox.critical(
                self,
                "AI初期化エラー",
                "AIモデルの読み込みに失敗しました。\n\n"
                "可能な原因:\n"
                "1. インターネット接続の問題（Hugging Faceへのアクセス不可）\n"
                "2. ファイアウォールによるブロック\n"
                "3. モデルファイルのダウンロード失敗\n\n"
                "解決方法:\n"
                "- オフラインモードを使用する（既にモデルがダウンロード済みの場合）\n"
                "- プロキシ設定を確認する\n"
                "- config.pyでHF_OFFLINE_MODE=Trueに設定する"
            )
            self._reset_ui()

    def on_features_ready(self, paths, tensor):
        if tensor is None:
            if self.is_processing:
                self.lbl_status.setText("ベクトル化失敗または停止されました")
            else:
                self.lbl_status.setText("ベクトル化失敗")
            self.progress.setRange(0, 100)
            self._reset_ui()
            return
        
        if not self.is_processing:
            # 停止された場合
            self.lbl_status.setText("処理が停止されました")
            self.progress.setRange(0, 100)
            self._reset_ui()
            return

        self.lbl_status.setText(f"AI解析完了。DBSCANでクラスタリング中...")

        try:
            # Tensor(GPU/CPU) を Numpy配列に変換
            X = tensor.cpu().numpy()

            # DBSCANアルゴリズムを実行
            # eps: 類似度の距離閾値 (小さいほど厳密。CLIPのコサイン距離なら0.1~0.2くらい)
            # min_samples: 最低何枚あればグループとみなすか (2枚以上)
            # metric: コサイン距離を使う ('cosine')
            db = DBSCAN(eps=config.DBSCAN_EPS, 
                       min_samples=config.DBSCAN_MIN_SAMPLES, 
                       metric='cosine').fit(X)

            labels = db.labels_  # 各画像のグループIDが入る [-1, 0, 0, 1, -1, 2...]

            # 結果をまとめる
            clusters = {}
            noise = []

            for path, label in zip(paths, labels):
                if label == -1:
                    noise.append(path)  # どこにも属さなかった孤独な写真
                else:
                    if label not in clusters: clusters[label] = []
                    clusters[label].append(path)

            # リスト形式に変換して表示へ
            sorted_clusters = list(clusters.values())
            self.display_clusters(sorted_clusters, noise)

        except Exception as e:
            logger.error(f"Clustering error: {e}", exc_info=True)
            self.lbl_status.setText(f"MLエラー: {e}")
            QMessageBox.critical(self, "エラー", f"クラスタリング処理中にエラーが発生しました:\n{e}")

        self.progress.setRange(0, 100)
        self._reset_ui()

    def display_clusters(self, clusters, noise):
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        self.lbl_status.setText(f"完了: {len(clusters)} グループを発見 ({len(noise)}枚は分類不能)")
        self._reset_ui()

        # グループ表示
        for i, group in enumerate(clusters):
            self.add_group_widget(f"✨ AIグループ {i + 1}", group)

        # ノイズ表示（オプション）
        if noise:
            self.add_group_widget(f"🗑️ その他 (分類不能)", noise, is_noise=True)

        self.scroll_layout.addStretch()

    def add_group_widget(self, title, files, is_noise=False):
        frame = QFrame()
        frame.setStyleSheet("background-color: #252526; border-radius: 5px; margin-bottom: 10px;")
        vbox = QVBoxLayout(frame)

        hbox = QHBoxLayout()
        lbl = QLabel(f"{title} ({len(files)}枚)")
        lbl.setStyleSheet(f"font-weight: bold; color: {'#888' if is_noise else '#fff'};")

        btn_move = QPushButton("移動...")
        btn_move.setFixedSize(80, 25)
        btn_move.setStyleSheet("background-color: #d83b01; color: white;")
        btn_move.clicked.connect(lambda _, f=files: self.move_group(f))

        hbox.addWidget(lbl)
        hbox.addStretch()
        hbox.addWidget(btn_move)
        vbox.addLayout(hbox)

        # サムネイル（最初の10枚）
        scroll_h = QScrollArea()
        scroll_h.setFixedHeight(120)
        scroll_h.setWidgetResizable(True)
        content_h = QWidget()
        layout_h = QHBoxLayout(content_h)
        layout_h.setContentsMargins(0, 0, 0, 0)

        for path in files[:12]:
            lbl_img = QLabel()
            pix = QPixmap(path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
            lbl_img.setPixmap(pix)
            layout_h.addWidget(lbl_img)

        layout_h.addStretch()
        scroll_h.setWidget(content_h)
        vbox.addWidget(scroll_h)
        self.scroll_layout.addWidget(frame)

    def move_group(self, file_paths):
        dest = QFileDialog.getExistingDirectory(self, "移動先フォルダ")
        if not dest: return

        text, ok = QInputDialog.getText(self, "フォルダ作成", "フォルダ名を入力:", text="")
        if ok and text:
            dest = os.path.join(dest, text)
            os.makedirs(dest, exist_ok=True)

        for src in file_paths:
            try:
                if not config.validate_path(src) or not config.validate_path(dest):
                    logger.warning(f"Invalid path for move: src={src}, dest={dest}")
                    continue
                shutil.move(src, os.path.join(dest, os.path.basename(src)))
            except (OSError, IOError, shutil.Error) as e:
                logger.error(f"Failed to move file {src} to {dest}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error moving file {src}: {e}", exc_info=True)

        QMessageBox.information(self, "完了", "移動しました")
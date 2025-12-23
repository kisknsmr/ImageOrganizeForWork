import sys
import os
import shutil
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFileDialog, QFrame, QScrollArea, QProgressBar,
                             QMessageBox, QInputDialog)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

# ★追加: インポート確認
try:
    from sklearn.cluster import DBSCAN

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

AI_AVAILABLE = True


class ClusteringPage(QWidget):
    def __init__(self):
        super().__init__()
        self.ai_worker = None
        self.target_files = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ヘッダー
        header = QHBoxLayout()
        self.lbl_title = QLabel("🤖 AI 自動グルーピング (DBSCAN Clustering)")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(self.lbl_title)

        self.btn_open = QPushButton("📂 フォルダを選択 (Max 1000枚)")
        self.btn_open.clicked.connect(self.select_folder)
        self.btn_open.setStyleSheet("background-color: #007acc; color: white; padding: 8px;")
        header.addWidget(self.btn_open)
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
            return

        if len(self.target_files) > 1000:
            QMessageBox.warning(self, "制限", "処理速度のため1000枚に制限します")
            self.target_files = self.target_files[:1000]

        self.lbl_status.setText(f"{len(self.target_files)} 枚の特徴量を抽出中...")
        self.progress.setRange(0, 0)
        self.start_ai_process()

    def start_ai_process(self):
        if self.ai_worker:
            self.ai_worker.vectorize_images(self.target_files)
            return

        try:
            from modules.ai_classifier import AIWorker
            self.ai_worker = AIWorker()
            self.ai_worker.model_loaded.connect(self.on_model_loaded)
            self.ai_worker.features_ready.connect(self.on_features_ready)
            self.ai_worker.start()
        except:
            self.lbl_status.setText("AI初期化エラー")

    def on_model_loaded(self, success):
        if success:
            self.ai_worker.vectorize_images(self.target_files)

    def on_features_ready(self, paths, tensor):
        if tensor is None:
            self.lbl_status.setText("ベクトル化失敗")
            self.progress.setRange(0, 100)
            return

        self.lbl_status.setText(f"AI解析完了。DBSCANでクラスタリング中...")

        try:
            # --- ★ここがAIライブラリ(scikit-learn)の出番 ---

            # Tensor(GPU/CPU) を Numpy配列に変換
            X = tensor.cpu().numpy()

            # DBSCANアルゴリズムを実行
            # eps: 類似度の距離閾値 (小さいほど厳密。CLIPのコサイン距離なら0.1~0.2くらい)
            # min_samples: 最低何枚あればグループとみなすか (2枚以上)
            # metric: コサイン距離を使う ('cosine')
            db = DBSCAN(eps=0.15, min_samples=2, metric='cosine').fit(X)

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
            self.lbl_status.setText(f"MLエラー: {e}")
            print(e)

        self.progress.setRange(0, 100)

    def display_clusters(self, clusters, noise):
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        self.lbl_status.setText(f"完了: {len(clusters)} グループを発見 ({len(noise)}枚は分類不能)")

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
                shutil.move(src, os.path.join(dest, os.path.basename(src)))
            except:
                pass

        QMessageBox.information(self, "完了", "移動しました")
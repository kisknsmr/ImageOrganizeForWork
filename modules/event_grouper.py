import os
import datetime
import logging
import numpy as np
from collections import defaultdict
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# sklearnのインポート確認
try:
    from sklearn.cluster import DBSCAN
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("sklearn not available, content-based grouping will be disabled")

class EventGrouper:
    def __init__(self, db_manager):
        self.db = db_manager

    def group_by_time(self, files, gap_hours=6):
        """
        Group files into events based on time gaps.

        Args:
            files: List of dicts with keys 'id', 'path', 'timestamp' (timestamp can be None).
            gap_hours: Minimum hours between files to split into a new event.

        Returns:
            List of events. Each event is a dict:
            {
                'start_time': datetime,
                'end_time': datetime,
                'files': [file_dict, ...],
                'count': int,
                'suggested_name': str,
                'ai_label': None
            }
        """
        if not files:
            return []

        no_date_files = []
        sorted_files = sorted(files, key=lambda x: x.get('timestamp') or 0)
        
        events = []
        current_event = []
        last_time = None
        
        gap_seconds = gap_hours * 3600

        for file_data in sorted_files:
            ts = file_data.get('timestamp')
            
            if not ts:
                no_date_files.append(file_data)
                continue

            # Convert to datetime if float/int
            try:
                dt = datetime.datetime.fromtimestamp(ts)
            except (ValueError, TypeError, OSError):
                no_date_files.append(file_data)
                continue
            except Exception as e:
                logger.warning("Unexpected error converting timestamp for file %s: %s", file_data.get('path', 'unknown'), e)
                no_date_files.append(file_data)
                continue

            if last_time is None:
                current_event.append(file_data)
                last_time = ts
                continue

            # Check gap
            if (ts - last_time) > gap_seconds:
                # Close current event
                if current_event:
                    events.append(self._finalize_event(current_event))
                current_event = [file_data]
            else:
                current_event.append(file_data)
            
            last_time = ts

        # Close final event
        if current_event:
            events.append(self._finalize_event(current_event))
            
        # Handle no-date files (put them in a separate "Unknown Date" group or multiple)
        if no_date_files:
            events.append({
                'start_time': None,
                'end_time': None,
                'files': no_date_files,
                'count': len(no_date_files),
                'suggested_name': "日付不明"
            })
            
        # Sort events by date descending (newest first)
        events.sort(key=lambda x: x['start_time'].timestamp() if x['start_time'] else 0, reverse=True)
        
        return events

    def _finalize_event(self, file_list):
        if not file_list:
            return None
            
        # Get start/end
        timestamps = [f.get('timestamp') for f in file_list]
        start_ts = min(timestamps)
        end_ts = max(timestamps)
        
        start_dt = datetime.datetime.fromtimestamp(start_ts)
        end_dt = datetime.datetime.fromtimestamp(end_ts)
        
        # Basic name suggestion based on date
        if start_dt.date() == end_dt.date():
            name = start_dt.strftime("%Y-%m-%d")
        else:
            name = f"{start_dt.strftime('%Y-%m-%d')}_{end_dt.strftime('%m-%d')}"
            
        return {
            'start_time': start_dt,
            'end_time': end_dt,
            'files': file_list,
            'count': len(file_list),
            'suggested_name': name,
            'ai_label': None
        }
    
    def group_by_content(self, files, ai_worker, eps=0.15, min_samples=2):
        """
        内容ベースで画像をグループ化（CLIP特徴量を使用したクラスタリング）
        
        Args:
            files: List of dicts with {'id', 'path', 'timestamp', ...}
            ai_worker: AIWorker instance (must be ready)
            eps: DBSCANのepsパラメータ（類似度の閾値）
            min_samples: DBSCANのmin_samplesパラメータ（最小クラスタサイズ）
            
        Returns:
            List of events (same format as group_by_time)
        """
        if not SKLEARN_AVAILABLE:
            logger.error("sklearn not available, cannot use content-based grouping")
            return []
        
        if not ai_worker or not ai_worker.ready:
            logger.warning("AI worker not ready, cannot use content-based grouping")
            return []
        
        if not files:
            return []
        
        logger.info(f"EventGrouper: Starting content-based grouping for {len(files)} files...")
        
        # 1. 画像パスを取得
        image_paths = [f['path'] for f in files]
        
        # 2. AIWorkerで特徴量を取得（非同期処理のため、同期版が必要）
        # ここでは簡易的に、各画像を個別にベクトル化する方法を使用
        # 実際の実装では、AIWorkerのvectorize_imagesを使用すべき
        try:
            # バッチ処理で特徴量を取得
            features_list = []
            valid_files = []
            
            # 画像を読み込んでベクトル化
            batch_size = 32
            for i in range(0, len(image_paths), batch_size):
                batch_paths = image_paths[i:i+batch_size]
                batch_files = files[i:i+batch_size]
                
                # AIWorkerでベクトル化（簡易版 - 実際には非同期処理が必要）
                # ここでは、AIWorkerの内部メソッドを直接呼び出すか、
                # 同期版のメソッドを追加する必要がある
                # 一旦、クラスタリングUIと同じ方法を使用
                valid_batch = []
                for p in batch_paths:
                    if os.path.exists(p):
                        valid_batch.append(p)
                
                if not valid_batch:
                    continue
                
                # AIWorkerのvectorize_imagesを使用（非同期なので、完了を待つ必要がある）
                # 簡易実装: 各画像を個別に処理
                batch_features = []
                for path in valid_batch:
                    try:
                        # predict_eventの内部ロジックを参考に、画像特徴量を取得
                        img = ai_worker.Image.open(path).convert('RGB')
                        img_inputs = ai_worker.proc(images=[img], return_tensors="pt", padding=True)
                        with ai_worker.torch.no_grad():
                            img_feat = ai_worker.mod.get_image_features(**img_inputs)
                            img_feat /= img_feat.norm(dim=-1, keepdim=True)
                        batch_features.append(img_feat.cpu().numpy()[0])
                        valid_files.append(batch_files[batch_paths.index(path)])
                    except Exception as e:
                        logger.warning(f"Failed to process {path}: {e}")
                        continue
                
                if batch_features:
                    features_list.extend(batch_features)
            
            if len(features_list) < min_samples:
                logger.warning(f"Not enough valid images for clustering ({len(features_list)} < {min_samples})")
                return []
            
            # 3. DBSCANクラスタリング
            features_array = np.array(features_list)
            clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
            labels = clustering.fit_predict(features_array)
            
            # 4. クラスタごとにイベントを作成
            events = []
            unique_labels = sorted([l for l in set(labels) if l != -1])  # ノイズを除いてソート
            
            for cluster_idx, label in enumerate(unique_labels):
                cluster_indices = [i for i, l in enumerate(labels) if l == label]
                cluster_files = [valid_files[i] for i in cluster_indices]
                
                # イベント情報を作成（日付ベースではなく、グループ番号を使用）
                if cluster_files:
                    events.append({
                        'start_time': None,  # 日付は使用しない
                        'end_time': None,
                        'files': cluster_files,
                        'count': len(cluster_files),
                        'suggested_name': f"グループ_{cluster_idx+1}",  # グループ番号を使用
                        'ai_label': None  # AIラベリングは後で追加される
                    })
            
            # ノイズファイルも1つのイベントとして追加
            noise_indices = [i for i, l in enumerate(labels) if l == -1]
            if noise_indices:
                noise_files = [valid_files[i] for i in noise_indices]
                if noise_files:
                    events.append({
                        'start_time': None,
                        'end_time': None,
                        'files': noise_files,
                        'count': len(noise_files),
                        'suggested_name': "ノイズ（未分類）",
                        'ai_label': None
                    })
            
            # 日付順ではなく、グループ番号順にソート（既にソート済みだが、念のため）
            # ノイズは最後に配置
            events.sort(key=lambda x: (x['suggested_name'] == "ノイズ（未分類）", x['suggested_name']))
            
            logger.info(f"EventGrouper: Content-based grouping created {len(events)} events")
            return events
            
        except Exception as e:
            logger.error(f"EventGrouper: Content-based grouping failed: {e}", exc_info=True)
            return []
    
    def group_by_hybrid(self, files, ai_worker, gap_hours=6, eps=0.15, min_samples=2):
        """
        ハイブリッドグループ化: 日付ベース + 内容ベース
        
        1. まず日付でグループ化
        2. 各日付グループ内で内容ベースのクラスタリングを実行
        3. 同じ日付でも内容が異なる場合は分割
        
        Args:
            files: List of dicts with {'id', 'path', 'timestamp', ...}
            ai_worker: AIWorker instance
            gap_hours: 日付グループ化の間隔（時間）
            eps: DBSCANのepsパラメータ
            min_samples: DBSCANのmin_samplesパラメータ
            
        Returns:
            List of events
        """
        if not files:
            return []
        
        logger.info(f"EventGrouper: Starting hybrid grouping for {len(files)} files...")
        
        # 1. まず日付でグループ化
        time_events = self.group_by_time(files, gap_hours=gap_hours)
        
        # 2. 各日付イベント内で内容ベースのクラスタリング
        final_events = []
        
        for time_event in time_events:
            event_files = time_event['files']
            
            if len(event_files) < min_samples:
                # ファイル数が少ない場合はそのまま追加
                final_events.append(time_event)
                continue
            
            # 内容ベースでクラスタリング
            content_events = self.group_by_content(event_files, ai_worker, eps=eps, min_samples=min_samples)
            
            if not content_events or len(content_events) == 1:
                # クラスタリングが失敗したか、1つのクラスタのみの場合は元のイベントを使用
                final_events.append(time_event)
            else:
                # 複数のクラスタに分割された場合、各クラスタを個別のイベントとして追加
                # 日付情報を保持
                for content_event in content_events:
                    # 元の日付情報を保持
                    if time_event.get('start_time'):
                        content_event['start_time'] = time_event['start_time']
                        content_event['end_time'] = time_event['end_time']
                        # 日付ベースの名前を更新
                        start_dt = time_event['start_time']
                        if time_event.get('end_time'):
                            end_dt = time_event['end_time']
                            if start_dt.date() == end_dt.date():
                                date_name = start_dt.strftime("%Y-%m-%d")
                            else:
                                date_name = f"{start_dt.strftime('%Y-%m-%d')}_{end_dt.strftime('%m-%d')}"
                        else:
                            date_name = start_dt.strftime("%Y-%m-%d")
                        content_event['suggested_name'] = date_name
                    final_events.append(content_event)
        
        logger.info(f"EventGrouper: Hybrid grouping created {len(final_events)} events")
        return final_events
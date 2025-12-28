import os
import datetime
from collections import defaultdict

class EventGrouper:
    def __init__(self, db_manager):
        self.db = db_manager

    def group_by_time(self, files, gap_hours=6):
        """
        Group files into events based on time gaps.
        
        Args:
            files: List of (id, path, timestamp) tuples. Timestamp can be None.
            gap_hours: Minimum hours between files to split into a new event.
            
        Returns:
            List of events. Each event is a dict:
            {
                'start_time': datetime,
                'end_time': datetime,
                'files': [ (id, path, timestamp), ... ],
                'count': int,
                'suggested_name': str (placeholder)
            }
        """
        if not files:
            return []

        # Filter out files without valid timestamps for special handling
        valid_files = []
        no_date_files = []
        
        for f in files:
            # f is expected to be (id, path, timestamp, ...)
            # Ensure timestamp is available
            ts = f[5] if len(f) > 5 else None # Assuming standard DB query format, need to verify or handle flexible input
            
            # If input is just (id, path), we need to fetch timestamp or use what's given
            # Let's assume the caller passes fully populated rows or we fetch.
            # For Safety: Let's assume input is list of dicts or objects if possible, but DB usually returns tuples.
            # Let's standardize: Input `files` should be list of dicts: {'id':.., 'path':.., 'timestamp':..}
            # OR, we sort strictly here.
            
            pass 
        
        # To make this robust, let's query the DB here if needed, or assume input is sorted.
        # But `files` might be loose. Let's try to get struct data.
        
        # ACTUALLY: It is better if this class converts DB rows to objects.
        # For now, let's implement the logic assuming sorted input of objects with 'timestamp'.
        
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
            except:
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

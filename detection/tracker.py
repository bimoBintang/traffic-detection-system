import time
from deep_sort_realtime.deepsort_tracker import DeepSort

class Track:
    def __init__(self, track_id, cls_name, bbox, center_curr):
        self.id = track_id
        self.cls_name = cls_name
        self.bbox = bbox
        self.center_prev = None
        self.center_curr = center_curr
        self.last_seen = time.time()
        self.is_active = True

class Tracker:
    def __init__(self, max_age=30):
        self.tracker = DeepSort(max_age=max_age, n_init=3)
        self.tracks = {}

    def update(self, detections, frame=None):
        if not detections:
            self._expire_tracks()
            return []
        
        # Format detections for DeepSORT: ([x, y, w, h], confidence, class)
        formatted = []
        for d in detections:
            x1, y1, x2, y2 = d['bbox']
            if x2 > x1 and y2 > y1:
                w, h = x2 - x1, y2 - y1
                # DeepSort expects: (bbox, confidence, class_name)
                formatted.append(([x1, y1, w, h], d['confidence'], d['class']))
        
        if not formatted:
            self._expire_tracks()
            return []
        
        # Update DeepSORT with frame parameter
        try:
            ds_tracks = self.tracker.update_tracks(formatted, frame=frame)
        except Exception as e:
            print(f"[ERROR] DeepSort update failed: {e}")
            # Return raw detections as fallback
            return self._convert_detections_to_tracks(detections)
        
        current_time = time.time()
        tracked_objects = []
        
        for ds_track in ds_tracks:
            if not ds_track.is_confirmed():
                continue
            
            track_id = ds_track.track_id
            x1, y1, x2, y2 = ds_track.to_ltrb()
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            cls_name = getattr(ds_track, 'det_class', 'vehicle')

            if track_id in self.tracks:
                track = self.tracks[track_id]
                track.center_prev = track.center_curr
                track.center_curr = center
                track.bbox = [int(x1), int(y1), int(x2), int(y2)]
                track.last_seen = current_time
                track.is_active = True
            else:
                track = Track(track_id, cls_name, [int(x1), int(y1), int(x2), int(y2)], center)
                self.tracks[track_id] = track
            
            tracked_objects.append({
                'track_id': track_id,
                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                'class': cls_name,
                'center': center
            })
        
        self._expire_tracks()
        return tracked_objects
    
    def _convert_detections_to_tracks(self, detections):
        """Fallback: convert detections to track format without DeepSort"""
        tracked_objects = []
        for i, detection in enumerate(detections):
            tracked_objects.append({
                'track_id': f"det_{i}",
                'bbox': detection['bbox'],
                'class': detection['class'],
                'center': detection['center']
            })
        return tracked_objects

    def _expire_tracks(self):
        current_time = time.time()
        expired = [tid for tid, track in self.tracks.items() 
                  if current_time - track.last_seen > 30]
        for tid in expired:
            del self.tracks[tid]

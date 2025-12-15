import cv2
import time
from collections import defaultdict

class LineCounter:
    def __init__(self, line_position=0.5):  # Changed to 50% (center of frame)
        self.line_position = line_position
        self.line_y = None
        
        # Required total_counts attribute
        self.total_counts = defaultdict(int)
        
        # Track crossing state
        self.crossed_tracks = set()
        self.track_positions = {}  # track_id -> previous_y
        
        # Debug mode
        self.debug = True
        
        # Class mapping
        self.class_map = {
            'car': 'Mobil',
            'motorcycle': 'Motor', 
            'bus': 'Bus',
            'truck': 'Truk'
        }
        
    def update(self, tracked_objects, frame):
        """Update counter with tracked objects and return frame with line"""
        h, w = frame.shape[:2]
        if self.line_y is None:
            self.line_y = int(h * self.line_position)
        
        # Draw counting line
        cv2.line(frame, (0, self.line_y), (w, self.line_y), (0, 255, 0), 2)
        cv2.putText(frame, "COUNTING LINE", (10, self.line_y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Draw total counts on frame
        count_text = f"Mobil:{self.total_counts['Mobil']} Motor:{self.total_counts['Motor']} Bus:{self.total_counts['Bus']} Truk:{self.total_counts['Truk']}"
        cv2.putText(frame, count_text, (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        # Process each tracked object
        for obj in tracked_objects:
            track_id = obj.get('track_id')
            if track_id is None:
                continue
                
            vehicle_class = obj.get('class', 'unknown')
            
            # Get center point
            if 'center' in obj:
                cx, cy = obj['center']
            elif 'bbox' in obj:
                x1, y1, x2, y2 = obj['bbox']
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            else:
                continue
            
            # Debug: Draw center point and distance to line
            if self.debug:
                cv2.circle(frame, (int(cx), int(cy)), 5, (0, 0, 255), -1)
                dist = int(cy - self.line_y)
                cv2.putText(frame, f"{dist}", (int(cx)+10, int(cy)), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            
            # Check for line crossing
            self._check_crossing(track_id, cy, vehicle_class)
        
        return frame
    
    def _check_crossing(self, track_id, current_y, vehicle_class):
        """Check if track crossed the counting line"""
        if track_id in self.crossed_tracks or vehicle_class not in self.class_map:
            return
        
        prev_y = self.track_positions.get(track_id)
        self.track_positions[track_id] = current_y
        
        if prev_y is not None and self.line_y is not None:
            # Count crossings in both directions
            crossed_down = prev_y < self.line_y and current_y >= self.line_y
            crossed_up = prev_y > self.line_y and current_y <= self.line_y
            
            if crossed_down or crossed_up:
                mapped_class = self.class_map[vehicle_class]
                self.total_counts[mapped_class] += 1
                self.crossed_tracks.add(track_id)
                direction = "↓" if crossed_down else "↑"
                print(f"[COUNT] {direction} {mapped_class}: {self.total_counts[mapped_class]} (Track {track_id})")
    
    def get_counts(self):
        """Get current counts dictionary"""
        return dict(self.total_counts)

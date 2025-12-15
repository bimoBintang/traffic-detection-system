#!/usr/bin/env python3
"""
Main Traffic Detection Service
Processes video frames, detects vehicles, stores data, handles streaming
"""
import cv2
import threading
import time
from datetime import datetime
from queue import Queue
import logging

from detection.yolo_detector import YOLODetector
from detection.line_counter import LineCounter
from database.db_manager import DatabaseManager
from config import Config

class TrafficDetectionService:
    def __init__(self, video_source="videoplayback.mp4"):
        self.video_source = video_source
        self.detector = YOLODetector()
        self.db_manager = DatabaseManager()
        self.line_counter = LineCounter()
        
        self.running = False
        self.frame_queue = Queue(maxsize=10)
        self.detection_thread = None
        self.capture_thread = None
        
        # Stats
        self.total_detections = 0
        self.fps_counter = 0
        self.last_fps_time = time.time()
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Start detection service"""
        if self.running:
            return
        
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
        self.detection_thread = threading.Thread(target=self._process_frames, daemon=True)
        
        self.capture_thread.start()
        self.detection_thread.start()
        
        self.logger.info("Traffic detection service started")

    def stop(self):
        """Stop detection service"""
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        if self.detection_thread:
            self.detection_thread.join(timeout=2)
        
        self.logger.info("Traffic detection service stopped")

    def _capture_frames(self):
        """Capture frames from video source"""
        cap = cv2.VideoCapture(self.video_source)
        if not cap.isOpened():
            self.logger.error(f"Cannot open video source: {self.video_source}")
            return

        frame_skip = 0
        while self.running:
            ret, frame = cap.read()
            if not ret:
                # Loop video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            
            # Skip frames for performance
            if frame_skip < Config.SKIP_FRAMES:
                frame_skip += 1
                continue
            frame_skip = 0
            
            # Add to queue if not full
            if not self.frame_queue.full():
                self.frame_queue.put(frame)
            
            time.sleep(1/Config.DEFAULT_FPS)
        
        cap.release()

    def _process_frames(self):
        """Process frames for vehicle detection"""
        camera_id = "main_camera"
        
        while self.running:
            if self.frame_queue.empty():
                time.sleep(0.01)
                continue
            
            frame = self.frame_queue.get()
            
            try:
                # Detect vehicles
                detections = self.detector.detect_vehicles(frame)
                
                if detections:
                    self.logger.info(f"Detected {len(detections)} vehicles")
                    
                    # Process each detection
                    for detection in detections:
                        # Save to database
                        detection_id = self.db_manager.save_detection(camera_id, detection)
                        if detection_id:
                            self.total_detections += 1
                            self.logger.debug(f"Saved detection ID: {detection_id}")
                    
                    # Update line counter
                    frame = self.line_counter.update(detections, frame)
                
                # Calculate FPS
                self._update_fps()
                
                # Optional: Display frame (for debugging)
                if hasattr(self, 'display_enabled') and self.display_enabled:
                    self._display_frame(frame, detections)
                
            except Exception as e:
                self.logger.error(f"Frame processing error: {e}")

    def _update_fps(self):
        """Update FPS counter"""
        self.fps_counter += 1
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            fps = self.fps_counter / (current_time - self.last_fps_time)
            self.logger.info(f"Processing FPS: {fps:.1f}, Total detections: {self.total_detections}")
            self.fps_counter = 0
            self.last_fps_time = current_time

    def _display_frame(self, frame, detections):
        """Display frame with detections (optional)"""
        display_frame = frame.copy()
        
        # Draw detections
        for detection in detections:
            bbox = detection['bbox']
            x1, y1, x2, y2 = bbox
            class_name = detection['class']
            confidence = detection['confidence']
            
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{class_name}: {confidence:.2f}"
            cv2.putText(display_frame, label, (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Add stats
        stats_text = f"Detections: {self.total_detections} | Time: {datetime.now().strftime('%H:%M:%S')}"
        cv2.putText(display_frame, stats_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        cv2.imshow('Traffic Detection', display_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.stop()

    def get_stats(self):
        """Get detection statistics"""
        return {
            'total_detections': self.total_detections,
            'running': self.running,
            'queue_size': self.frame_queue.qsize(),
            'unsynced_count': self.db_manager.get_unsync_count() if self.db_manager else 0
        }

    def enable_display(self, enabled=True):
        """Enable/disable frame display"""
        self.display_enabled = enabled

def main():
    """Run detection service standalone"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Traffic Detection Service')
    parser.add_argument('--video', default='videoplayback.mp4', help='Video source')
    parser.add_argument('--display', action='store_true', help='Show detection window')
    args = parser.parse_args()
    
    service = TrafficDetectionService(args.video)
    
    if args.display:
        service.enable_display(True)
    
    try:
        service.start()
        
        # Keep running and show stats
        while service.running:
            time.sleep(5)
            stats = service.get_stats()
            print(f"Stats: {stats}")
            
    except KeyboardInterrupt:
        print("\nStopping detection service...")
    finally:
        service.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

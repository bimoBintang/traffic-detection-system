import torch
from ultralytics import YOLO
import cv2
from config import Config

class YOLODetector:
    def __init__(self):
        try:
            # Force CPU and disable optimizations to fix uniform_() error
            torch.set_num_threads(1)
            self.model = YOLO(Config.MODEL_PATH)
            self.model.to('cpu')
            # Disable model optimizations that cause the error
            self.model.model.eval()
            print("[INFO] YOLO model loaded successfully")
        except Exception as e:
            print(f"[ERROR] YOLO loading failed: {e}")
            raise e
        
        self.vehicle_classes = Config.VEHICLE_CLASSES

    def detect_vehicles(self, frame):
        with torch.no_grad():  # Disable gradients for inference
            results = self.model(frame, conf=Config.CONFIDENCE_THRESHOLD, verbose=False)
        detections = []

        for r in results:
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    if cls in self.vehicle_classes:
                        x1, y1, x2, y2 = box.xyxy[0]
                        detections.append({
                            "bbox": [int(x1), int(y1), int(x2), int(y2)],
                            "class": self.vehicle_classes[cls],
                            "confidence": conf,
                            "center": ((int(x1) + int(x2)) / 2, (int(y1) + int(y2)) / 2),
                        })

        return detections

    def detect_and_draw(self, frame):
        detections = self.detect_vehicles(frame)
        annotated_frame = frame.copy()
        
        for detection in detections:
            bbox = detection["bbox"]
            class_name = detection["class"]
            confidence = detection["confidence"]
            
            cv2.rectangle(annotated_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            label = f"{class_name}: {confidence:.2f}"
            cv2.putText(annotated_frame, label, (bbox[0], bbox[1] - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
        return annotated_frame, detections

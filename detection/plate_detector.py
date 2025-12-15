# detection/plate_detector.py
"""
License Plate Detection and OCR Module
Uses OpenCV for plate localization and EasyOCR for text recognition
"""
import cv2
import numpy as np
import re
import logging
from typing import Optional, Dict, Tuple, List

# Lazy load EasyOCR to avoid slow startup
_ocr_reader = None

def get_ocr_reader():
    """Lazy initialization of EasyOCR reader"""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            _ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            logging.info("[PLATE] EasyOCR initialized successfully")
        except Exception as e:
            logging.error(f"[PLATE] Failed to initialize EasyOCR: {e}")
            return None
    return _ocr_reader


class PlateDetector:
    """License Plate Detection and OCR"""
    
    def __init__(self):
        self.min_plate_width = 60
        self.min_plate_height = 20
        self.max_plate_width = 300
        self.max_plate_height = 100
        
        # Indonesian plate pattern: 1-2 letters + 1-4 numbers + 1-3 letters
        # Examples: B 1234 XYZ, AB 123 CD, B 1 A
        self.plate_pattern = re.compile(r'^[A-Z]{1,2}\s*\d{1,4}\s*[A-Z]{1,3}$')
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("[PLATE] PlateDetector initialized")
    
    def detect_plate(self, frame: np.ndarray, vehicle_bbox: List[int]) -> Optional[Dict]:
        """
        Detect license plate within vehicle bounding box
        
        Args:
            frame: Full video frame
            vehicle_bbox: [x1, y1, x2, y2] of detected vehicle
            
        Returns:
            Dict with plate info or None if not detected
        """
        try:
            x1, y1, x2, y2 = vehicle_bbox
            
            # Expand search area slightly
            padding = 10
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(frame.shape[1], x2 + padding)
            y2 = min(frame.shape[0], y2 + padding)
            
            # Crop vehicle region
            vehicle_roi = frame[y1:y2, x1:x2]
            
            if vehicle_roi.size == 0:
                return None
            
            # Focus on lower half of vehicle (where plates usually are)
            h = vehicle_roi.shape[0]
            lower_roi = vehicle_roi[int(h * 0.4):, :]
            
            # Find plate candidates
            plate_candidates = self._find_plate_candidates(lower_roi)
            
            if not plate_candidates:
                return None
            
            # Try OCR on each candidate
            for plate_img, (px1, py1, px2, py2) in plate_candidates:
                plate_text, confidence = self._read_plate_text(plate_img)
                
                if plate_text and confidence > 0.3:
                    # Calculate absolute position
                    abs_x1 = x1 + px1
                    abs_y1 = y1 + int(h * 0.4) + py1
                    abs_x2 = x1 + px2
                    abs_y2 = y1 + int(h * 0.4) + py2
                    
                    return {
                        'plate_number': plate_text,
                        'confidence': confidence,
                        'bbox': [abs_x1, abs_y1, abs_x2, abs_y2]
                    }
            
            return None
            
        except Exception as e:
            self.logger.debug(f"[PLATE] Detection error: {e}")
            return None
    
    def _find_plate_candidates(self, roi: np.ndarray) -> List[Tuple[np.ndarray, Tuple]]:
        """Find potential plate regions using contour analysis"""
        candidates = []
        
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            
            # Apply bilateral filter to reduce noise while keeping edges
            gray = cv2.bilateralFilter(gray, 11, 17, 17)
            
            # Edge detection
            edges = cv2.Canny(gray, 30, 200)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                # Approximate contour
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.018 * peri, True)
                
                # Plates typically have 4 corners
                if len(approx) >= 4 and len(approx) <= 8:
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Check aspect ratio (plates are typically wide)
                    aspect_ratio = w / float(h) if h > 0 else 0
                    
                    if (2.0 <= aspect_ratio <= 6.0 and
                        self.min_plate_width <= w <= self.max_plate_width and
                        self.min_plate_height <= h <= self.max_plate_height):
                        
                        plate_img = roi[y:y+h, x:x+w]
                        if plate_img.size > 0:
                            candidates.append((plate_img, (x, y, x+w, y+h)))
            
            # Sort by area (larger first)
            candidates.sort(key=lambda x: x[0].shape[0] * x[0].shape[1], reverse=True)
            
            return candidates[:3]  # Return top 3 candidates
            
        except Exception as e:
            self.logger.debug(f"[PLATE] Candidate search error: {e}")
            return []
    
    def _read_plate_text(self, plate_img: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Read text from plate image using EasyOCR
        
        Returns:
            Tuple of (cleaned_text, confidence)
        """
        try:
            reader = get_ocr_reader()
            if reader is None:
                return None, 0.0
            
            # Preprocess plate image
            plate_img = self._preprocess_plate(plate_img)
            
            # Run OCR
            results = reader.readtext(plate_img, detail=1)
            
            if not results:
                return None, 0.0
            
            # Combine all detected text
            full_text = ""
            total_conf = 0.0
            
            for (bbox, text, conf) in results:
                full_text += text + " "
                total_conf += conf
            
            avg_conf = total_conf / len(results) if results else 0.0
            
            # Clean and validate plate text
            cleaned = self._clean_plate_text(full_text)
            
            if cleaned:
                return cleaned, avg_conf
            
            return None, 0.0
            
        except Exception as e:
            self.logger.debug(f"[PLATE] OCR error: {e}")
            return None, 0.0
    
    def _preprocess_plate(self, plate_img: np.ndarray) -> np.ndarray:
        """Preprocess plate image for better OCR"""
        try:
            # Resize for better OCR
            height = 100
            aspect = plate_img.shape[1] / plate_img.shape[0]
            width = int(height * aspect)
            plate_img = cv2.resize(plate_img, (width, height))
            
            # Convert to grayscale
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
            
            # Apply CLAHE for contrast enhancement
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
            # Threshold
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            return thresh
            
        except Exception:
            return plate_img
    
    def _clean_plate_text(self, text: str) -> Optional[str]:
        """Clean and validate plate text"""
        # Remove special characters, keep only letters, numbers, spaces
        cleaned = re.sub(r'[^A-Za-z0-9\s]', '', text)
        cleaned = cleaned.upper().strip()
        
        # Remove extra spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Must be reasonable length for Indonesian plates
        if len(cleaned) < 3 or len(cleaned) > 12:
            return None
        
        # Basic validation - should start with letter and contain numbers
        if cleaned and cleaned[0].isalpha() and any(c.isdigit() for c in cleaned):
            # Format it nicely with no spaces (for storage)
            return cleaned.replace(' ', '')
        
        return None


def draw_plate_detection(frame: np.ndarray, plate_info: Dict) -> np.ndarray:
    """Draw plate detection on frame"""
    if not plate_info:
        return frame
    
    bbox = plate_info.get('bbox', [])
    plate_number = plate_info.get('plate_number', '')
    confidence = plate_info.get('confidence', 0)
    
    if bbox and len(bbox) == 4:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        
        # Draw plate bounding box (yellow)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        
        # Draw plate number label
        label = f"{plate_number} ({confidence:.0%})"
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        
        # Background for text
        cv2.rectangle(frame, 
                     (x1, y1 - label_size[1] - 10), 
                     (x1 + label_size[0] + 10, y1), 
                     (0, 255, 255), -1)
        
        # Text
        cv2.putText(frame, label, (x1 + 5, y1 - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    
    return frame

# camera/camera_manager_exe.py
import cv2
import threading
from queue import Queue
import time
import sys
import os

class CameraManager:
    def __init__(self):
        self.cameras = {}
        self.threads = {}
        
    def _get_safe_backends(self):
        """Get safe OpenCV backends for EXE"""
        if sys.platform == "win32":
            return [cv2.CAP_DSHOW]  # Most reliable on Windows
        else:
            return [cv2.CAP_V4L2, cv2.CAP_ANY]
    
    def _test_webcam(self, index):
        """Test webcam with EXE-safe method"""
        backends = self._get_safe_backends()
        
        for backend in backends:
            cap = None
            try:
                cap = cv2.VideoCapture()
                cap.open(index, backend)
                
                if cap.isOpened():
                    # Minimal test
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        cap.release()
                        return True
                
                if cap:
                    cap.release()
            except:
                if cap:
                    try:
                        cap.release()
                    except:
                        pass
        
        return False
    
    def add_camera(self, camera_id, source):
        """Add camera with EXE compatibility"""
        if isinstance(source, int) and not self._test_webcam(source):
            raise Exception(f"Webcam {source} not accessible")
        
        self.cameras[camera_id] = {
            'source': source,
            'frame_queue': Queue(maxsize=1),
            'active': True,
            'last_frame': None
        }
        self._start_capture(camera_id)
    
    def get_frame(self, camera_id):
        """Get latest frame"""
        if camera_id not in self.cameras:
            return None
        
        camera_data = self.cameras[camera_id]
        
        # Get latest frame
        frame = None
        while not camera_data['frame_queue'].empty():
            try:
                frame = camera_data['frame_queue'].get_nowait()
            except:
                break
        
        if frame is not None:
            camera_data['last_frame'] = frame
        
        return camera_data['last_frame']
    
    def _start_capture(self, camera_id):
        """Start capture thread"""
        thread = threading.Thread(
            target=self._capture_frames,
            args=(camera_id,),
            daemon=True
        )
        thread.start()
        self.threads[camera_id] = thread
    
    def _capture_frames(self, camera_id):
        """Capture frames safely for EXE"""
        cap = None
        source = self.cameras[camera_id]['source']
        
        try:
            # Use safe backend
            if isinstance(source, int):
                backends = self._get_safe_backends()
                for backend in backends:
                    try:
                        cap = cv2.VideoCapture()
                        cap.open(source, backend)
                        if cap.isOpened():
                            break
                        cap.release()
                    except:
                        if cap:
                            cap.release()
            else:
                cap = cv2.VideoCapture(source)
            
            if not cap or not cap.isOpened():
                print(f"Failed to open camera {camera_id}")
                return
            
            # Set properties
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            while self.cameras[camera_id]['active']:
                try:
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        # Clear queue and add new frame
                        while not self.cameras[camera_id]['frame_queue'].empty():
                            try:
                                self.cameras[camera_id]['frame_queue'].get_nowait()
                            except:
                                break
                        
                        try:
                            self.cameras[camera_id]['frame_queue'].put_nowait(frame)
                        except:
                            pass
                    
                    time.sleep(0.033)  # ~30 FPS
                except:
                    time.sleep(0.1)
        
        except Exception as e:
            print(f"Camera error: {e}")
        finally:
            if cap:
                try:
                    cap.release()
                except:
                    pass
    
    def remove_camera(self, camera_id):
        """Remove camera"""
        if camera_id in self.cameras:
            self.cameras[camera_id]['active'] = False
            if camera_id in self.threads:
                self.threads[camera_id].join(timeout=1)
            del self.cameras[camera_id]

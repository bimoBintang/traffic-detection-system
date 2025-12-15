# camera/camera_manager.py
import cv2
import threading
from queue import Queue
import socket
import time
import sys
import os
import platform

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

# Determine backends based on OS
_SYSTEM = platform.system()
if _SYSTEM == "Darwin":  # macOS
    _BACKENDS = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
elif _SYSTEM == "Windows":
    _BACKENDS = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
else:  # Linux
    _BACKENDS = [cv2.CAP_V4L2, cv2.CAP_ANY]

class CameraManager:
    def __init__(self):
        self.cameras = {}
        self.threads = {}
        self.active = {}
        
    def discover_cameras(self, subnet="192.168.1"):
        """Discover RTSP cameras on local network"""
        cameras = []
        common_ports = [554, 8554]
        
        for i in range(1, 255):
            ip = f"{subnet}.{i}"
            for port in common_ports:
                if self._test_rtsp(ip, port):
                    cameras.append(f"rtsp://{ip}:{port}/stream")
        
        return cameras
    
    def _test_rtsp(self, ip, port, timeout=0.5):
        """Test if RTSP port is open"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def add_camera(self, camera_id, source):
        """Add a new camera source with webcam validation"""
        if camera_id not in self.cameras:
            # Test webcam access before adding
            if isinstance(source, int):
                if not self._test_webcam(source):
                    raise Exception(f"Cannot access webcam at index {source}")
            
            self.cameras[camera_id] = {
                'source': source,
                'frame_queue': Queue(maxsize=2),
                'active': True,
                'last_frame': None,
                'fps': 0
            }
            self._start_capture(camera_id)
    
    def _test_webcam(self, index):
        """Test if webcam is accessible with safe error handling"""
        for backend in _BACKENDS:
            cap = None
            try:
                # Create capture with timeout
                cap = cv2.VideoCapture(index, backend)
                
                # Set properties before testing
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    
                    # Test frame read with timeout
                    for attempt in range(3):
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            print(f"[INFO] Webcam {index} works with backend {backend}")
                            cap.release()
                            return True
                        
                cap.release()
            except Exception as e:
                print(f"[DEBUG] Backend {backend} failed: {e}")
                if cap:
                    try:
                        cap.release()
                    except:
                        pass
        
        print(f"[ERROR] Webcam {index} not accessible with any backend")
        return False
    
    def remove_camera(self, camera_id):
        """Remove a camera and stop its thread"""
        if camera_id in self.cameras:
            # Stop the capture thread
            self.cameras[camera_id]['active'] = False
            
            # Wait for thread to finish
            if camera_id in self.threads:
                self.threads[camera_id].join(timeout=2)
                del self.threads[camera_id]
            
            # Remove camera data
            del self.cameras[camera_id]
    
    def get_frame(self, camera_id):
        """Get the latest frame from camera (non-blocking)"""
        if camera_id not in self.cameras:
            return None
            
        camera_data = self.cameras[camera_id]
        
        # Try to get new frame from queue
        frame = None
        
        # Empty the queue and get the latest frame
        while not camera_data['frame_queue'].empty():
            try:
                frame = camera_data['frame_queue'].get_nowait()
                camera_data['last_frame'] = frame
            except:
                break
        
        # If no new frame, return the last frame
        if frame is None:
            frame = camera_data['last_frame']
            
        return frame
    
    def _start_capture(self, camera_id):
        """Start capture thread for a camera"""
        thread = threading.Thread(
            target=self._capture_frames,
            args=(camera_id,),
            daemon=True
        )
        thread.start()
        self.threads[camera_id] = thread
    
    def _capture_frames(self, camera_id):
        """Capture frames from camera in a separate thread"""
        cap = None
        retry_count = 0
        max_retries = 3
        frame_count = 0
        start_time = time.time()
        
        while self.cameras[camera_id]['active'] and retry_count < max_retries:
            try:
                # Open video capture
                if cap is None or not cap.isOpened():
                    source = self.cameras[camera_id]['source']
                    
                    # For webcam (integer source), try multiple backends
                    if isinstance(source, int):
                        # Use OS-appropriate backends
                        cap_opened = False
                        
                        for backend in _BACKENDS:
                            try:
                                cap = cv2.VideoCapture()
                                cap.open(source, backend)
                                
                                if cap.isOpened():
                                    # Set minimal properties to avoid errors
                                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                                    
                                    # Test frame read with exception handling
                                    try:
                                        ret, test_frame = cap.read()
                                        if ret and test_frame is not None:
                                            cap_opened = True
                                            break
                                    except Exception:
                                        pass
                                
                                cap.release()
                            except Exception:
                                if cap:
                                    try:
                                        cap.release()
                                    except:
                                        pass
                        
                        if not cap_opened:
                            print(f"[ERROR] Camera {camera_id} not accessible")
                            retry_count += 1
                            time.sleep(2)
                            continue
                    else:
                        # For streams, use default
                        cap = cv2.VideoCapture(source)
                    #
                    # Optimization settings for different sources
                    if isinstance(self.cameras[camera_id]['source'], str):
                        if self.cameras[camera_id]['source'].startswith('rtsp://'):
                            # RTSP optimizations
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('H', '2', '6', '4'))
                            # Use TCP instead of UDP for more reliable streaming
                            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                        elif self.cameras[camera_id]['source'].startswith('http://'):
                            # HTTP stream optimizations
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    else:
                        # Webcam optimizations
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        cap.set(cv2.CAP_PROP_FPS, 30)
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)
                    
                    if not cap.isOpened():
                        print(f"Failed to open camera {camera_id}")
                        retry_count += 1
                        time.sleep(2)
                        continue
                
                # Read frame with timeout and error handling
                try:
                    ret, frame = cap.read()
                    
                    if ret and frame is not None and frame.size > 0:
                        # Calculate FPS
                        frame_count += 1
                        elapsed_time = time.time() - start_time
                        if elapsed_time > 1.0:
                            self.cameras[camera_id]['fps'] = frame_count / elapsed_time
                            frame_count = 0
                            start_time = time.time()
                        
                        # Resize frame for performance
                        try:
                            frame = cv2.resize(frame, (Config.FRAME_WIDTH, Config.FRAME_HEIGHT))
                        except:
                            # If resize fails, use original frame
                            pass
                        
                        # Drop old frames and add new one
                        if self.cameras[camera_id]['frame_queue'].full():
                            try:
                                self.cameras[camera_id]['frame_queue'].get_nowait()
                            except:
                                pass
                        
                        self.cameras[camera_id]['frame_queue'].put(frame)
                        retry_count = 0  # Reset retry count on successful read
                        
                        # Small sleep to prevent CPU overload
                        time.sleep(0.033)  # ~30 FPS
                    else:
                        print(f"Failed to read frame from {camera_id}")
                        retry_count += 1
                        time.sleep(0.5)
                        
                except Exception as e:
                    print(f"OpenCV exception in {camera_id}: {e}")
                    retry_count += 1
                    time.sleep(1)
                    # Try to recreate capture on OpenCV errors
                    if cap:
                        try:
                            cap.release()
                        except:
                            pass
                        cap = None
                    
            except Exception as e:
                print(f"Error capturing from {camera_id}: {e}")
                retry_count += 1
                time.sleep(1)
        
        # Clean up
        if cap is not None:
            cap.release()
        print(f"Stopped capturing from {camera_id}")
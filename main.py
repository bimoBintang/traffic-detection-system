#!/usr/bin/env python3
"""
EXE-compatible main file with webcam fixes
"""
import os
import sys
import logging

# EXE compatibility fixes
if hasattr(sys, '_MEIPASS'):
    # Running in PyInstaller bundle
    os.environ['OPENCV_VIDEOIO_PRIORITY_MSMF'] = '0'
    os.environ['OPENCV_VIDEOIO_PRIORITY_DSHOW'] = '1'

# Configure logging for EXE
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('traffic_detection.log', mode='w')
    ]
)

def setup_opencv():
    """Setup OpenCV for EXE"""
    try:
        import cv2
        cv2.setNumThreads(2)
        cv2.setUseOptimized(True)
        logging.info("OpenCV initialized for EXE")
        return True
    except Exception as e:
        logging.error(f"OpenCV setup failed: {e}")
        return False

def main():
    logging.info("Starting Traffic Detection System (EXE)")
    
    # Setup OpenCV
    if not setup_opencv():
        input("Press Enter to exit...")
        return
    
    try:
        # Import config
        from config import Config
        
        # Use EXE-compatible camera manager
        if hasattr(sys, '_MEIPASS'):
            from camera.camera_manager_exe import CameraManager
        else:
            from camera.camera_manager import CameraManager
        
        # Test webcam
        camera_manager = CameraManager()
        
        print("Testing webcam access...")
        
        # Try multiple camera indices
        webcam_found = False
        for cam_id in range(3):  # Try cameras 0, 1, 2
            try:
                print(f"Trying camera {cam_id}...")
                camera_manager.add_camera("test", cam_id)
                
                # Wait a moment for camera to initialize
                import time
                time.sleep(1)
                
                frame = camera_manager.get_frame("test")
                if frame is not None:
                    print(f"✅ Webcam {cam_id} working!")
                    camera_manager.remove_camera("test")
                    webcam_found = True
                    break
                else:
                    camera_manager.remove_camera("test")
                    
            except Exception as e:
                print(f"Camera {cam_id} failed: {e}")
                try:
                    camera_manager.remove_camera("test")
                except:
                    pass
        
        if not webcam_found:
            print("❌ No working webcam found")
            print("\nOptions:")
            print("1. Connect USB camera and restart")
            print("2. Use video file instead")
            choice = input("Enter choice (1/2) or press Enter to exit: ").strip()
            
            if choice == "2":
                # Use existing video file
                video_path = "videoplayback.mp4"
                if os.path.exists(video_path):
                    print(f"Using video file: {video_path}")
                    camera_manager.add_camera("video", video_path)
                else:
                    print("Video file not found")
                    input("Press Enter to exit...")
                    return
            else:
                return
        
        # Start dashboard
        from dashboard.app import TrafficDashboard
        app = TrafficDashboard()
        app.run()
        
    except Exception as e:
        logging.error(f"Application error: {e}")
        print(f"Error: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()

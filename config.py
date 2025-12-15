import os
from datetime import datetime

class Config:
    # Database
    DB_PATH = "traffic_data.db"
    
    # YOLO Model
    MODEL_PATH = "yolov8n.pt"  # Use the existing model
    CONFIDENCE_THRESHOLD = 0.3  # Increased for better accuracy
    
    # Vehicle Classes (COCO dataset - correct IDs)
    VEHICLE_CLASSES = {
        2: "car",        # Car
        3: "motorcycle", # Motorcycle  
        5: "bus",        # Bus
        7: "truck"       # Truck
    }
    
    # Camera Settings
    CAMERA_SOURCES = []  # Will be populated dynamically
    DEFAULT_FPS = 30
    FRAME_WIDTH = 1280
    FRAME_HEIGHT = 720
    
    # Performance Settings
    SKIP_FRAMES = 2  
    MAX_DETECTION_FPS = 15  
    
    # Detection Line
    LINE_POSITION = 0.6  
    
    # Export
    EXPORT_PATH = "exports/"
    
    # Plate Detection Settings
    PLATE_DETECTION_ENABLED = True
    PLATE_CONFIDENCE_THRESHOLD = 0.3
    PLATE_MIN_WIDTH = 60
    PLATE_MIN_HEIGHT = 20
    
    # Firebase Configuration (Realtime Database)
    FIREBASE_ENABLED = True   # Set True untuk enable Firebase sync
    FIREBASE_CREDENTIALS = "database/fb-credentials.json"  # Path ke service account JSON
    FIREBASE_URL = "https://traffic-detection-30212-default-rtdb.asia-southeast1.firebasedatabase.app/"  # RTDB URL
    
    # Firebase Sync Settings
    FIREBASE_SYNC_INTERVAL = 30  # Seconds
    FIREBASE_BATCH_SIZE = 50     
    FIREBASE_RETRY_ATTEMPTS = 3  
    
    # Data Retention
    LOCAL_DATA_RETENTION_DAYS = 7    
    FIREBASE_DATA_RETENTION_DAYS = 365  
    
    AUTO_CLEANUP_SYNCED = True   
    SYNC_ON_DETECTION = False    
    BATCH_SYNC_ENABLED = True    
    
    # Threading
    USE_GPU = True  
    NUM_THREADS = 4  
    
    # Network Settings
    CONNECTION_TIMEOUT = 10  
    MAX_RETRIES = 3          
    
    @classmethod
    def is_online_mode(cls):
        return cls.FIREBASE_ENABLED and os.path.exists(cls.FIREBASE_CREDENTIALS)
    
    @classmethod
    def get_firebase_config_status(cls):
        status = {
            'enabled': cls.FIREBASE_ENABLED,
            'credentials_file_exists': os.path.exists(cls.FIREBASE_CREDENTIALS),
            'ready': False
        }
        
        if status['enabled'] and status['credentials_file_exists']:
            status['ready'] = True
        
        return status

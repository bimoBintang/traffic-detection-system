import firebase_admin
from firebase_admin import credentials, db
from config import Config
from datetime import datetime, date
import os

class FirebaseSync:
    def __init__(self):
        self.enabled = Config.FIREBASE_ENABLED
        self.db = None

        if self.enabled:
            try:
                # Check credentials file exists
                if not os.path.exists(Config.FIREBASE_CREDENTIALS):
                    print(f"[Firebase ERROR] Credentials file not found: {Config.FIREBASE_CREDENTIALS}")
                    self.enabled = False
                    return
                
                if not firebase_admin._apps:
                    cred = credentials.Certificate(Config.FIREBASE_CREDENTIALS)
                    firebase_admin.initialize_app(cred, {
                        'databaseURL': Config.FIREBASE_URL
                    })
                self.db = db
                print("[Firebase RTDB] Connected successfully")
                self.test_connection()
            except Exception as e:
                print(f"[Firebase ERROR] Initialization failed: {e}")
                self.enabled = False

    def test_connection(self):
        try:
            ref = self.db.reference('system/connection_test')
            ref.set({
                'test_time': datetime.now().isoformat(),
                'status': 'connected'
            })
            print("[Firebase RTDB] Connection test successful")
            return True
        except Exception as e:
            print(f"[Firebase ERROR] Connection test failed: {e}")
            self.enabled = False
            return False

    def sync_detection(self, detection_data: dict):
        """Simpan 1 deteksi kendaraan ke RTDB"""
        if not self.enabled:
            return False
        try:
            doc_id = f"{detection_data['camera_id']}_{detection_data['local_id']}"
            ref = self.db.reference('detections').child(doc_id)
            ref.set({
                **detection_data,
                'firebase_sync_time': datetime.now().isoformat()
            })
            return True
        except Exception as e:
            print(f"[Firebase ERROR] sync_detection: {e}")
            return False

    def sync_daily_summary(self, camera_id: str, target_date: date, summary_data: dict):
        """Simpan ringkasan harian ke RTDB"""
        if not self.enabled:
            return False
        try:
            doc_id = f"{camera_id}_{target_date.strftime('%Y%m%d')}"
            ref = self.db.reference('daily_summaries').child(doc_id)
            ref.set({
                'camera_id': camera_id,
                'date': target_date.isoformat(),
                'cars': summary_data.get('car', 0),
                'motorcycles': summary_data.get('motorcycle', 0),
                'buses': summary_data.get('bus', 0),
                'trucks': summary_data.get('truck', 0),
                'total': summary_data.get('total', 0),
                'last_updated': datetime.now().isoformat()
            })
            return True
        except Exception as e:
            print(f"[Firebase ERROR] sync_daily_summary: {e}")
            return False

    def get_daily_summary_from_firebase(self, target_date: date, camera_ids=None):
        """Ambil summary harian dari RTDB"""
        if not self.enabled:
            return []
        try:
            ref = self.db.reference('daily_summaries')
            data = ref.get()
            if not data:
                return []
            
            summaries = []
            for doc_id, value in data.items():
                if value.get('date') == target_date.isoformat():
                    if not camera_ids or value.get('camera_id') in camera_ids:
                        summaries.append(value)
            return summaries
        except Exception as e:
            print(f"[Firebase ERROR] get_daily_summary_from_firebase: {e}")
            return []

    def get_connection_status(self):
        if not self.enabled:
            return {'status': 'disabled', 'message': 'Firebase sync is disabled'}
        try:
            ref = self.db.reference('system/connection_test')
            test_doc = ref.get()
            return {
                'status': 'connected',
                'message': 'Firebase RTDB connection active',
                'last_test': datetime.now().isoformat(),
                'last_value': test_doc
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Firebase connection failed: {str(e)}',
                'last_test': datetime.now().isoformat()
            }

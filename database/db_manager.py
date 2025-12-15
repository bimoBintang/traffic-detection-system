# database/db_manager.py
from sqlalchemy import create_engine, and_, text
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime, date, timedelta
import pandas as pd
import os
import threading
import time
import json

from .models import Base, VehicleDetection, DailySummary, PlateDetection
from .firebase_sync import FirebaseSync
from config import Config


class DatabaseManager:
    def __init__(self):
        # Engine & Session
        self.engine = create_engine(f"sqlite:///{Config.DB_PATH}", echo=False)
        
        # Check and migrate database schema
        self._migrate_database()
        
        Base.metadata.create_all(self.engine)
        session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(session_factory)
        
        # Firebase sync
        self.firebase = FirebaseSync()
        self.sync_lock = threading.Lock()
        
        # Auto-sync thread untuk upload ke Firebase
        self.start_auto_sync()
    
    def _migrate_database(self):
        """Add missing columns to existing database"""
        try:
            with self.engine.connect() as conn:
                # Check if synced_to_firebase column exists
                result = conn.execute(text("PRAGMA table_info(vehicle_detections)"))
                columns = [row[1] for row in result]
                
                if 'synced_to_firebase' not in columns:
                    conn.execute(text("ALTER TABLE vehicle_detections ADD COLUMN synced_to_firebase BOOLEAN DEFAULT 0"))
                    conn.commit()
                    print("[INFO] Added synced_to_firebase column to database")
        except Exception as e:
            print(f"[INFO] Database migration: {e}")
        
        # Track pending sync items
        self.pending_sync = []

    def save_detection(self, camera_id, detection):
        """Save detection ke SQLite dan mark untuk Firebase sync"""
        session = self.Session()
        try:
            vehicle = VehicleDetection(
                camera_id=camera_id,
                vehicle_type=detection.get("class", "unknown"),
                confidence=float(detection.get("confidence", 0.0)),
                timestamp=datetime.now(),
                synced_to_firebase=False  # Mark as not synced yet
            )
            session.add(vehicle)
            session.commit()
            
            # Update daily summary
            self.update_daily_summary(camera_id, detection.get("class"))
            
            print(f"[DB] Saved detection ID: {vehicle.id}")
            return vehicle.id
            
        except Exception as e:
            session.rollback()
            print(f"[DB ERROR] save_detection: {e}")
            return None
        finally:
            session.close()

    def save_plate_detection(self, camera_id: str, plate_number: str, 
                             vehicle_type: str = None, confidence: float = 0.0):
        """Save license plate detection to database"""
        session = self.Session()
        try:
            plate = PlateDetection(
                camera_id=camera_id,
                plate_number=plate_number.upper().replace(' ', ''),
                vehicle_type=vehicle_type,
                confidence=float(confidence),
                timestamp=datetime.now(),
                synced_to_firebase=False
            )
            session.add(plate)
            session.commit()
            
            print(f"[DB] Saved plate: {plate.plate_number} (ID: {plate.id})")
            return plate.id
            
        except Exception as e:
            session.rollback()
            print(f"[DB ERROR] save_plate_detection: {e}")
            return None
        finally:
            session.close()

    def get_plate_history(self, camera_id: str = None, limit: int = 50):
        """Get recent plate detection history"""
        session = self.Session()
        try:
            query = session.query(PlateDetection).order_by(
                PlateDetection.timestamp.desc()
            )
            
            if camera_id:
                query = query.filter_by(camera_id=camera_id)
            
            return query.limit(limit).all()
        finally:
            session.close()

    def search_plate(self, plate_number: str, exact: bool = False):
        """Search for a plate number in database"""
        session = self.Session()
        try:
            cleaned = plate_number.upper().replace(' ', '')
            
            if exact:
                results = session.query(PlateDetection).filter_by(
                    plate_number=cleaned
                ).order_by(PlateDetection.timestamp.desc()).all()
            else:
                results = session.query(PlateDetection).filter(
                    PlateDetection.plate_number.like(f'%{cleaned}%')
                ).order_by(PlateDetection.timestamp.desc()).all()
            
            return results
        finally:
            session.close()

    def get_plate_count_today(self, camera_id: str = None):
        """Get count of unique plates detected today"""
        session = self.Session()
        try:
            today_start = datetime.combine(datetime.now().date(), datetime.min.time())
            
            query = session.query(PlateDetection.plate_number).filter(
                PlateDetection.timestamp >= today_start
            ).distinct()
            
            if camera_id:
                query = query.filter_by(camera_id=camera_id)
            
            return query.count()
        finally:
            session.close()


    def update_daily_summary(self, camera_id, vehicle_type):
        """Update summary harian per camera"""
        session = self.Session()
        today = datetime.now().date()

        try:
            summary = (
                session.query(DailySummary)
                .filter_by(date=today, camera_id=camera_id)
                .first()
            )

            if not summary:
                summary = DailySummary(
                    date=today, 
                    camera_id=camera_id,
                    cars=0, motorcycles=0, buses=0, trucks=0
                )
                session.add(summary)

            # Update count berdasarkan jenis kendaraan
            if vehicle_type == "car":
                summary.cars += 1
            elif vehicle_type == "motorcycle":
                summary.motorcycles += 1
            elif vehicle_type == "bus":
                summary.buses += 1
            elif vehicle_type == "truck":
                summary.trucks += 1

            session.commit()
            
        except Exception as e:
            session.rollback()
            print(f"[DB ERROR] update_daily_summary: {e}")
        finally:
            session.close()

    def get_daily_summary(self, target_date, camera_ids=None):
        """
        Get daily summary dengan opsi filter camera
        Args:
            target_date: date object untuk tanggal yang diminta
            camera_ids: list camera IDs untuk filter (None = semua camera)
        """
        session = self.Session()
        try:
            query = session.query(DailySummary).filter_by(date=target_date)
            
            if camera_ids:
                query = query.filter(DailySummary.camera_id.in_(camera_ids))
            
            return query.all()
        finally:
            session.close()

    def get_combined_summary(self, target_date, camera_ids=None):
        """
        Get gabungan summary dari semua camera untuk satu hari
        Returns: dict dengan total count per vehicle type
        """
        summaries = self.get_daily_summary(target_date, camera_ids)
        
        combined = {
            'car': 0,
            'motorcycle': 0, 
            'bus': 0,
            'truck': 0,
            'total': 0
        }
        
        for summary in summaries:
            combined['car'] += summary.cars
            combined['motorcycle'] += summary.motorcycles
            combined['bus'] += summary.buses
            combined['truck'] += summary.trucks
        
        combined['total'] = sum([combined['car'], combined['motorcycle'], 
                               combined['bus'], combined['truck']])
        
        return combined

    def get_camera_summary(self, target_date, camera_id):
        """Get summary untuk camera tertentu"""
        session = self.Session()
        try:
            summary = (
                session.query(DailySummary)
                .filter_by(date=target_date, camera_id=camera_id)
                .first()
            )
            
            if summary:
                return {
                    'camera_id': camera_id,
                    'date': target_date,
                    'car': summary.cars,
                    'motorcycle': summary.motorcycles,
                    'bus': summary.buses,
                    'truck': summary.trucks,
                    'total': summary.cars + summary.motorcycles + summary.buses + summary.trucks
                }
            else:
                return {
                    'camera_id': camera_id,
                    'date': target_date,
                    'car': 0, 'motorcycle': 0, 'bus': 0, 'truck': 0, 'total': 0
                }
        finally:
            session.close()

    def get_date_range_summary(self, start_date, end_date, camera_ids=None):
        """Get summary untuk range tanggal"""
        session = self.Session()
        try:
            query = session.query(DailySummary).filter(
                and_(
                    DailySummary.date >= start_date,
                    DailySummary.date <= end_date
                )
            )
            
            if camera_ids:
                query = query.filter(DailySummary.camera_id.in_(camera_ids))
            
            return query.all()
        finally:
            session.close()

    def start_auto_sync(self):
        """Start background thread untuk sync ke Firebase"""
        if not self.firebase.enabled:
            return
        
        def sync_worker():
            while True:
                try:
                    self.sync_to_firebase()
                    time.sleep(30)  # Sync setiap 30 detik
                except Exception as e:
                    print(f"[SYNC ERROR] {e}")
                    time.sleep(60)  # Retry setelah 1 menit jika error
        
        sync_thread = threading.Thread(target=sync_worker, daemon=True)
        sync_thread.start()
        print("[DB] Auto-sync thread started")

    def sync_to_firebase(self):
        """Sync unsynced data ke Firebase dan hapus yang sudah sync"""
        if not self.firebase.enabled:
            return
        
        session = self.Session()
        try:
            with self.sync_lock:
                # Ambil data yang belum di-sync (max 100 records per batch)
                unsynced = (
                    session.query(VehicleDetection)
                    .filter_by(synced_to_firebase=False)
                    .order_by(VehicleDetection.timestamp.asc())
                    .limit(100)
                    .all()
                )
                
                if not unsynced:
                    return
                
                print(f"[SYNC] Syncing {len(unsynced)} records to Firebase...")
                
                synced_ids = []
                for detection in unsynced:
                    # Prepare data untuk Firebase
                    firebase_data = {
                        'id': detection.id,
                        'camera_id': detection.camera_id,
                        'vehicle_type': detection.vehicle_type,
                        'confidence': detection.confidence,
                        'timestamp': detection.timestamp.isoformat(),
                        'date': detection.timestamp.date().isoformat(),
                        'hour': detection.timestamp.hour
                    }
                    
                    # Upload ke Firebase
                    if self.firebase.sync_detection(firebase_data):
                        synced_ids.append(detection.id)
                    else:
                        break  # Stop jika ada error upload
                
                # Hapus records yang berhasil di-sync
                if synced_ids:
                    session.query(VehicleDetection).filter(
                        VehicleDetection.id.in_(synced_ids)
                    ).delete(synchronize_session=False)
                    
                    session.commit()
                    print(f"[SYNC] Successfully synced and removed {len(synced_ids)} records")
                
        except Exception as e:
            session.rollback()
            print(f"[SYNC ERROR] {e}")
        finally:
            session.close()

    def get_unsync_count(self):
        """Get jumlah data yang belum di-sync"""
        session = self.Session()
        try:
            return session.query(VehicleDetection).filter_by(synced_to_firebase=False).count()
        finally:
            session.close()

    def force_sync_all(self):
        """Force sync semua data yang belum ter-sync"""
        if not self.firebase.enabled:
            print("[SYNC] Firebase not enabled")
            return False
        
        session = self.Session()
        try:
            unsynced_count = session.query(VehicleDetection).filter_by(synced_to_firebase=False).count()
            print(f"[SYNC] Force syncing {unsynced_count} records...")
            
            # Sync dalam batch
            batch_size = 50
            total_synced = 0
            
            while True:
                batch = (
                    session.query(VehicleDetection)
                    .filter_by(synced_to_firebase=False)
                    .limit(batch_size)
                    .all()
                )
                
                if not batch:
                    break
                
                synced_ids = []
                for detection in batch:
                    firebase_data = {
                        'id': detection.id,
                        'camera_id': detection.camera_id,
                        'vehicle_type': detection.vehicle_type,
                        'confidence': detection.confidence,
                        'timestamp': detection.timestamp.isoformat(),
                        'date': detection.timestamp.date().isoformat(),
                        'hour': detection.timestamp.hour
                    }
                    
                    if self.firebase.sync_detection(firebase_data):
                        synced_ids.append(detection.id)
                
                # Remove synced records
                if synced_ids:
                    session.query(VehicleDetection).filter(
                        VehicleDetection.id.in_(synced_ids)
                    ).delete(synchronize_session=False)
                    session.commit()
                    total_synced += len(synced_ids)
                    print(f"[SYNC] Progress: {total_synced}/{unsynced_count}")
                
                time.sleep(0.1)  # Small delay between batches
            
            print(f"[SYNC] Force sync completed: {total_synced} records")
            return True
            
        except Exception as e:
            session.rollback()
            print(f"[SYNC ERROR] force_sync_all: {e}")
            return False
        finally:
            session.close()

    def export_to_csv(self, target_date, camera_ids=None):
        """Export data ke CSV dengan opsi filter camera"""
        session = self.Session()
        try:
            start = datetime.combine(target_date, datetime.min.time())
            end = datetime.combine(target_date, datetime.max.time())

            query = session.query(VehicleDetection).filter(
                VehicleDetection.timestamp.between(start, end)
            )
            
            if camera_ids:
                query = query.filter(VehicleDetection.camera_id.in_(camera_ids))

            detections = query.all()

            data = []
            for d in detections:
                data.append({
                    "timestamp": d.timestamp,
                    "camera_id": d.camera_id,
                    "vehicle_type": d.vehicle_type,
                    "confidence": d.confidence,
                })

            df = pd.DataFrame(data)
            os.makedirs(Config.EXPORT_PATH, exist_ok=True)
            
            # Generate filename with camera info
            if camera_ids and len(camera_ids) == 1:
                filename = f"traffic_data_{camera_ids[0]}_{target_date.strftime('%Y%m%d')}.csv"
            else:
                filename = f"traffic_data_all_cameras_{target_date.strftime('%Y%m%d')}.csv"
            
            filepath = os.path.join(Config.EXPORT_PATH, filename)
            df.to_csv(filepath, index=False)

            return filepath
        finally:
            session.close()

    def get_statistics_by_hour(self, target_date, camera_ids=None):
        """Get statistik per jam untuk dashboard"""
        session = self.Session()
        try:
            start = datetime.combine(target_date, datetime.min.time())
            end = datetime.combine(target_date, datetime.max.time())

            query = session.query(VehicleDetection).filter(
                VehicleDetection.timestamp.between(start, end)
            )
            
            if camera_ids:
                query = query.filter(VehicleDetection.camera_id.in_(camera_ids))

            detections = query.all()

            # Group by hour
            hourly_stats = {}
            for hour in range(24):
                hourly_stats[hour] = {'car': 0, 'motorcycle': 0, 'bus': 0, 'truck': 0}

            for detection in detections:
                hour = detection.timestamp.hour
                vehicle_type = detection.vehicle_type
                if hour in hourly_stats and vehicle_type in hourly_stats[hour]:
                    hourly_stats[hour][vehicle_type] += 1

            return hourly_stats
        finally:
            session.close()

    def cleanup_old_data(self, days_to_keep=7):
        """Cleanup data SQLite yang sudah lama (untuk optimasi)"""
        session = self.Session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            # Hapus detection lama yang sudah di-sync
            deleted = session.query(VehicleDetection).filter(
                and_(
                    VehicleDetection.timestamp < cutoff_date,
                    VehicleDetection.synced_to_firebase == True
                )
            ).delete()
            
            session.commit()
            print(f"[CLEANUP] Removed {deleted} old synced records")
            
        except Exception as e:
            session.rollback()
            print(f"[CLEANUP ERROR] {e}")
        finally:
            session.close()

    def get_sync_status(self):
        """Get status sync untuk monitoring"""
        session = self.Session()
        try:
            total_records = session.query(VehicleDetection).count()
            unsynced_records = session.query(VehicleDetection).filter_by(synced_to_firebase=False).count()
            
            return {
                'total_records': total_records,
                'unsynced_records': unsynced_records,
                'sync_percentage': round((total_records - unsynced_records) / max(total_records, 1) * 100, 2),
                'firebase_enabled': self.firebase.enabled
            }
        finally:
            session.close()

    def start_auto_sync(self):
        """Start background sync thread"""
        if not self.firebase.enabled:
            print("[SYNC] Firebase disabled, auto-sync not started")
            return
        
        def sync_worker():
            while True:
                try:
                    self.sync_to_firebase()
                    
                    # Cleanup old data setiap 1 jam
                    if datetime.now().minute == 0:
                        self.cleanup_old_data()
                    
                    time.sleep(30)  # Sync interval
                except Exception as e:
                    print(f"[SYNC WORKER ERROR] {e}")
                    time.sleep(60)
        
        sync_thread = threading.Thread(target=sync_worker, daemon=True)
        sync_thread.start()
        print("[SYNC] Auto-sync worker started")

    def sync_to_firebase(self):
        """Sync unsynced data ke Firebase"""
        if not self.firebase.enabled:
            return False
        
        session = self.Session()
        try:
            with self.sync_lock:
                # Batch sync untuk efisiensi
                unsynced = (
                    session.query(VehicleDetection)
                    .filter_by(synced_to_firebase=False)
                    .order_by(VehicleDetection.timestamp.asc())
                    .limit(50)  # Process 50 records per batch
                    .all()
                )
                
                if not unsynced:
                    return True
                
                synced_ids = []
                for detection in unsynced:
                    firebase_data = {
                        'local_id': detection.id,
                        'camera_id': detection.camera_id,
                        'vehicle_type': detection.vehicle_type,
                        'confidence': detection.confidence,
                        'timestamp': detection.timestamp.isoformat(),
                        'date': detection.timestamp.date().isoformat(),
                        'hour': detection.timestamp.hour,
                        'sync_time': datetime.now().isoformat()
                    }
                    
                    if self.firebase.sync_detection(firebase_data):
                        synced_ids.append(detection.id)
                    else:
                        break  # Stop on first error
                
                # Mark as synced (tapi jangan hapus dulu, biarkan cleanup yang handle)
                if synced_ids:
                    session.query(VehicleDetection).filter(
                        VehicleDetection.id.in_(synced_ids)
                    ).update({'synced_to_firebase': True}, synchronize_session=False)
                    
                    session.commit()
                    print(f"[SYNC] Marked {len(synced_ids)} records as synced")
                
                return len(synced_ids) > 0
                
        except Exception as e:
            session.rollback()
            print(f"[SYNC ERROR] {e}")
            return False
        finally:
            session.close()

    def close(self):
        """Close database connections"""
        self.Session.remove()
        print("[DB] Database connections closed")
# database/__init__.py

from .models import Base, VehicleDetection, DailySummary, PlateDetection
from .db_manager import DatabaseManager
from .firebase_sync import FirebaseSync

__all__ = [
    'Base',
    'VehicleDetection',
    'DailySummary',
    'PlateDetection',
    'DatabaseManager',
    'FirebaseSync'
]
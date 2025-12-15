# database/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class VehicleDetection(Base):
    __tablename__ = 'vehicle_detections'
    
    id = Column(Integer, primary_key=True)
    camera_id = Column(String(50), nullable=False, index=True)
    vehicle_type = Column(String(20), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    synced_to_firebase = Column(Boolean, default=False, index=True)  # Track sync status
    
    def __repr__(self):
        return f"<VehicleDetection(id={self.id}, camera={self.camera_id}, type={self.vehicle_type})>"

class DailySummary(Base):
    __tablename__ = 'daily_summaries'
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    camera_id = Column(String(50), nullable=False, index=True)
    cars = Column(Integer, default=0)
    motorcycles = Column(Integer, default=0)
    buses = Column(Integer, default=0)
    trucks = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<DailySummary(date={self.date}, camera={self.camera_id})>"
    
    @property
    def total_vehicles(self):
        return self.cars + self.motorcycles + self.buses + self.trucks

class CameraSettings(Base):
    __tablename__ = 'camera_settings'
    
    id = Column(Integer, primary_key=True)
    camera_id = Column(String(50), nullable=False, unique=True, index=True)
    source = Column(String(255), nullable=False)
    line_position = Column(Float, default=0.6)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<CameraSettings(camera_id={self.camera_id}, active={self.is_active})>"


class PlateDetection(Base):
    """License Plate Detection Records"""
    __tablename__ = 'plate_detections'
    
    id = Column(Integer, primary_key=True)
    camera_id = Column(String(50), nullable=False, index=True)
    plate_number = Column(String(20), nullable=False, index=True)
    vehicle_type = Column(String(20))
    confidence = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    synced_to_firebase = Column(Boolean, default=False, index=True)
    
    def __repr__(self):
        return f"<PlateDetection(id={self.id}, plate={self.plate_number})>"
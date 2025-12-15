# dashboard/app.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import threading
from PIL import Image, ImageTk
import cv2
from collections import defaultdict
import sys
import os

# Add parent directory to path to import from other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camera.camera_manager import CameraManager
from detection.yolo_detector import YOLODetector
from detection.line_counter import LineCounter
from database.db_manager import DatabaseManager
from detection.tracker import Tracker
from detection.plate_detector import PlateDetector, draw_plate_detection
from config import Config

class TrafficDashboard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Traffic Detection System")
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Set window size to 90% of screen
        window_width = int(screen_width * 0.9)
        window_height = int(screen_height * 0.9)
        self.root.geometry(f"{window_width}x{window_height}")
        
        # Center window
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Initialize only UI-related variables
        self.current_camera = None
        self.view_mode = "single"
        self.detection_running = False
        self.detection_thread = None
        
        # Heavy components - initialize as None
        self.camera_manager = None
        self.detector = None
        self.line_counters = {}
        self.db_manager = None
        self.trackers = {}
        self.plate_detector = None
        self.recent_plates = {}  # {cam_id: [(plate_number, timestamp), ...]}
        
        self.setup_ui()
        
        # Schedule heavy initialization after GUI is shown
        self.root.after(100, self.initialize_components)
        
    def initialize_components(self):
        """Initialize heavy components after GUI is displayed"""
        try:
            self.camera_manager = CameraManager()
            self.detector = YOLODetector()
            self.db_manager = DatabaseManager()
            
            # Initialize plate detector if enabled
            if Config.PLATE_DETECTION_ENABLED:
                try:
                    self.plate_detector = PlateDetector()
                    print("[INFO] Plate detector initialized")
                except Exception as e:
                    print(f"[WARNING] Plate detector not available: {e}")
                    self.plate_detector = None
            
            # Initialize line counters for any existing cameras
            for cam_id in self.camera_manager.cameras:
                if cam_id not in self.line_counters:
                    self.line_counters[cam_id] = LineCounter()
                if cam_id not in self.trackers:
                    self.trackers[cam_id] = Tracker()
            
            # Add default test camera if no cameras exist
            if not self.camera_manager.cameras:
                self._detect_webcams()
            
            self.start_detection()
            
        except Exception as e:
            print(f"[ERROR] Component initialization failed: {e}")
        
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top Control Panel
        control_frame = ttk.LabelFrame(main_frame, text="Controls", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 1: Date and Data Controls
        row1_frame = ttk.Frame(control_frame)
        row1_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(row1_frame, text="Select Date:").pack(side=tk.LEFT, padx=(0, 5))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.date_picker = ttk.Entry(row1_frame, textvariable=self.date_var, width=15)
        self.date_picker.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(row1_frame, text="Load Data", command=self.load_date_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)
        
        # Detection control buttons
        self.start_btn = ttk.Button(row1_frame, text="Start Detection", command=self.start_detection)
        self.start_btn.pack(side=tk.LEFT, padx=10)
        
        self.stop_btn = ttk.Button(row1_frame, text="Stop Detection", command=self.stop_detection, state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Row 2: Camera Controls
        row2_frame = ttk.Frame(control_frame)
        row2_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(row2_frame, text="Add Camera", command=self.add_camera_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2_frame, text="Scan Network", command=self.scan_network).pack(side=tk.LEFT, padx=5)
        
        # Camera selector
        ttk.Label(row2_frame, text="Select Camera:").pack(side=tk.LEFT, padx=(20, 5))
        self.camera_selector = ttk.Combobox(row2_frame, width=20, state="readonly")
        self.camera_selector.pack(side=tk.LEFT, padx=5)
        self.camera_selector.bind("<<ComboboxSelected>>", self.on_camera_selected)
        
        # View mode toggle
        self.view_mode_var = tk.StringVar(value="single")
        ttk.Radiobutton(row2_frame, text="Single View", variable=self.view_mode_var, 
                       value="single", command=self.toggle_view_mode).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(row2_frame, text="Grid View", variable=self.view_mode_var, 
                       value="grid", command=self.toggle_view_mode).pack(side=tk.LEFT, padx=5)
        
        # Main content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side - Statistics
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Vehicle Count Statistics
        stats_frame = ttk.LabelFrame(left_frame, text="Vehicle Count", padding="20")
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.stats_labels = {}
        vehicles = [('car', 'Mobil', '#2196F3'), 
                   ('motorcycle', 'Motor', '#4CAF50'), 
                   ('bus', 'Bus', '#FF9800'), 
                   ('truck', 'Truk', '#F44336')]
        
        for i, (vehicle, name, color) in enumerate(vehicles):
            row_frame = ttk.Frame(stats_frame)
            row_frame.pack(fill=tk.X, pady=5)
            
            # Vehicle icon placeholder
            icon_label = tk.Label(row_frame, text="🚗🏍️🚌🚛"[i], font=("Arial", 20))
            icon_label.pack(side=tk.LEFT, padx=(0, 10))
            
            # Vehicle name
            name_label = ttk.Label(row_frame, text=f"{name}:", font=("Arial", 14))
            name_label.pack(side=tk.LEFT, padx=(0, 10))
            
            # Count
            count_label = tk.Label(row_frame, text="0", font=("Arial", 18, "bold"), fg=color)
            count_label.pack(side=tk.LEFT)
            self.stats_labels[vehicle] = count_label
        
        # Camera List
        camera_list_frame = ttk.LabelFrame(left_frame, text="Active Cameras", padding="10")
        camera_list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Camera listbox with scrollbar
        list_scroll = ttk.Scrollbar(camera_list_frame)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.camera_listbox = tk.Listbox(camera_list_frame, yscrollcommand=list_scroll.set, 
                                        font=("Arial", 12), height=10)
        self.camera_listbox.pack(fill=tk.BOTH, expand=True)
        list_scroll.config(command=self.camera_listbox.yview)
        
        # Bind double-click to select camera
        self.camera_listbox.bind("<Double-Button-1>", self.on_listbox_double_click)
        
        # Right side - Camera Display
        self.camera_display_frame = ttk.LabelFrame(content_frame, text="Camera Feed", padding="10")
        self.camera_display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Single camera view (default)
        self.single_camera_label = tk.Label(self.camera_display_frame, text="No Camera Selected", 
                                          bg="black", fg="white", font=("Arial", 24))
        self.single_camera_label.pack(fill=tk.BOTH, expand=True)
        
        # Grid view container (hidden by default)
        self.grid_container = ttk.Frame(self.camera_display_frame)
        self.camera_labels = {}
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
    def toggle_view_mode(self):
        """Switch between single and grid view"""
        self.view_mode = self.view_mode_var.get()
        
        if self.view_mode == "single":
            self.grid_container.pack_forget()
            self.single_camera_label.pack(fill=tk.BOTH, expand=True)
        else:
            self.single_camera_label.pack_forget()
            self.grid_container.pack(fill=tk.BOTH, expand=True)
            self.update_grid_view()
    
    def update_grid_view(self):
        """Update grid view with all cameras"""
        # Clear existing widgets
        for widget in self.grid_container.winfo_children():
            widget.destroy()
        
        # Create canvas with scrollbar for grid
        canvas = tk.Canvas(self.grid_container, bg="gray20")
        scrollbar = ttk.Scrollbar(self.grid_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Calculate grid dimensions
        num_cameras = len(self.camera_manager.cameras)
        cols = 3  # 3 columns for grid view
        
        self.camera_labels.clear()
        
        for i, cam_id in enumerate(self.camera_manager.cameras):
            row = i // cols
            col = i % cols
            
            # Camera container
            cam_frame = ttk.Frame(scrollable_frame, relief=tk.RAISED, borderwidth=2)
            cam_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            # Camera title
            title_label = ttk.Label(cam_frame, text=cam_id, font=("Arial", 10, "bold"))
            title_label.pack(pady=5)
            
            # Camera display
            cam_label = tk.Label(cam_frame, text="Loading...", width=40, height=20,
                               bg="black", fg="white")
            cam_label.pack(padx=5, pady=5)
            self.camera_labels[cam_id] = cam_label
            
            # Configure grid weights
            scrollable_frame.rowconfigure(row, weight=1)
            scrollable_frame.columnconfigure(col, weight=1)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def on_camera_selected(self, event=None):
        """Handle camera selection from combobox"""
        selected = self.camera_selector.get()
        if selected and selected in self.camera_manager.cameras:
            self.current_camera = selected
            self.status_var.set(f"Viewing: {selected}")
    
    def on_listbox_double_click(self, event):
        """Handle double-click on camera list"""
        selection = self.camera_listbox.curselection()
        if selection:
            cam_id = self.camera_listbox.get(selection[0])
            self.camera_selector.set(cam_id)
            self.on_camera_selected()
            
            # Switch to single view if in grid mode
            if self.view_mode == "grid":
                self.view_mode_var.set("single")
                self.toggle_view_mode()
    
    def _detect_webcams(self):
        """Detect available webcams with robust error handling"""
        import cv2
        import platform
        
        print("[INFO] Scanning for webcams...")
        found_cameras = 0
        
        # Use correct backend based on OS
        system = platform.system()
        if system == "Darwin":  # macOS
            backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
        elif system == "Windows":
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        else:  # Linux
            backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
        
        print(f"[INFO] OS: {system}, backends: {backends}")
        
        # Test camera indices 0-2 (most common)
        for i in range(3):
            for backend in backends:
                cap = None
                try:
                    print(f"[DEBUG] Testing camera {i} with backend {backend}")
                    cap = cv2.VideoCapture(i, backend)
                    
                    if cap.isOpened():
                        # Set safe properties
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        
                        # Test multiple frame reads
                        success = False
                        for attempt in range(3):
                            try:
                                ret, frame = cap.read()
                                if ret and frame is not None and frame.size > 0:
                                    success = True
                                    break
                            except Exception as e:
                                print(f"[DEBUG] Frame read failed: {e}")
                                break
                        
                        if success:
                            cam_id = f"Webcam_{i}"
                            try:
                                self.camera_manager.add_camera(cam_id, i)
                                self.line_counters[cam_id] = LineCounter()
                                self.trackers[cam_id] = Tracker()
                                found_cameras += 1
                                print(f"[INFO] Added {cam_id} using backend {backend}")
                                cap.release()
                                break  # Success, try next camera
                            except Exception as e:
                                print(f"[ERROR] Failed to add camera {cam_id}: {e}")
                    
                    cap.release()
                    
                except Exception as e:
                    print(f"[DEBUG] Backend {backend} exception: {e}")
                    if cap:
                        try:
                            cap.release()
                        except:
                            pass
        
        if found_cameras > 0:
            self.update_camera_list()
            self.update_camera_selector()
            print(f"[INFO] Successfully added {found_cameras} webcam(s)")
        else:
            print("[WARNING] No working webcams found")
            print("  Solutions:")
            print("  1. Close other camera applications")
            print("  2. Check camera permissions")
            print("  3. Try different USB ports")
            print("  4. Restart the application")

    def add_camera_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Camera")
        dialog.geometry("450x300")
        
        # Center the dialog
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Camera ID:", font=("Arial", 12)).grid(row=0, column=0, padx=15, pady=15, sticky="w")
        id_entry = ttk.Entry(dialog, width=30, font=("Arial", 12))
        id_entry.grid(row=0, column=1, padx=15, pady=15)
        id_entry.insert(0, f"Camera_{len(self.camera_manager.cameras) + 1}")
        
        ttk.Label(dialog, text="Source:", font=("Arial", 12)).grid(row=1, column=0, padx=15, pady=15, sticky="w")
        source_entry = ttk.Entry(dialog, width=30, font=("Arial", 12))
        source_entry.grid(row=1, column=1, padx=15, pady=15)
        
        # Source examples
        examples_frame = ttk.LabelFrame(dialog, text="Examples", padding="10")
        examples_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=15, sticky="ew")
        
        examples = [
            "• Webcam: 0 (or 1, 2 for multiple webcams)",
            "• RTSP: rtsp://192.168.1.100:554/stream",
            "• Video File: /path/to/video.mp4",
            "• HTTP Stream: http://192.168.1.100:8080/video"
        ]
        
        for example in examples:
            ttk.Label(examples_frame, text=example, font=("Arial", 10)).pack(anchor="w", pady=2)
        
        def add_camera():
            cam_id = id_entry.get()
            source = source_entry.get()
            
            if cam_id and source:
                try:
                    # Convert "0" to integer for webcam
                    if source.isdigit():
                        source = int(source)
                    
                    self.camera_manager.add_camera(cam_id, source)
                    self.line_counters[cam_id] = LineCounter()
                    self.trackers[cam_id] = Tracker()
                    
                    # Update UI
                    self.update_camera_list()
                    self.update_camera_selector()
                    
                    # Auto-select the new camera
                    self.camera_selector.set(cam_id)
                    self.on_camera_selected()
                    
                    dialog.destroy()
                    self.status_var.set(f"Added camera: {cam_id}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to add camera: {str(e)}")
        
        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="Add Camera", command=add_camera).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=10)
    
    def update_camera_list(self):
        """Update the camera listbox"""
        self.camera_listbox.delete(0, tk.END)
        for cam_id in self.camera_manager.cameras:
            self.camera_listbox.insert(tk.END, cam_id)
    
    def update_camera_selector(self):
        """Update the camera combobox"""
        cameras = list(self.camera_manager.cameras.keys())
        self.camera_selector['values'] = cameras
        
        # Select first camera if none selected
        if not self.current_camera and cameras:
            self.camera_selector.set(cameras[0])
            self.on_camera_selected()
    
    def scan_network(self):
        self.status_var.set("Scanning network for cameras...")
        
        def scan():
            cameras = self.camera_manager.discover_cameras()
            
            self.root.after(0, lambda: self.status_var.set(f"Found {len(cameras)} cameras"))
            
            if cameras:
                for i, cam_url in enumerate(cameras):
                    cam_id = f"Network_Camera_{i+1}"
                    self.root.after(0, lambda url=cam_url, id=cam_id: self.add_discovered_camera(id, url))
        
        threading.Thread(target=scan, daemon=True).start()
    
    def add_discovered_camera(self, cam_id, source):
        response = messagebox.askyesno("Camera Found", 
                                     f"Found camera at:\n{source}\n\nAdd as '{cam_id}'?")
        if response:
            self.camera_manager.add_camera(cam_id, source)
            self.line_counters[cam_id] = LineCounter()
            self.trackers[cam_id] = Tracker()
            self.update_camera_list()
            self.update_camera_selector()
    
    def _draw_bounding_boxes(self, frame, tracked_objects):
        """Draw bounding boxes and labels for all tracked objects"""
        import cv2
        
        colors = {
            'car': (0, 255, 255),        # Yellow
            'motorcycle': (0, 255, 0),   # Green
            'bus': (255, 165, 0),        # Orange
            'truck': (0, 0, 255),        # Red
            'vehicle': (255, 255, 255)   # White
        }
        
        for obj in tracked_objects:
            # Handle different bbox formats
            if 'bbox' in obj:
                bbox = obj['bbox']
                x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            else:
                continue
                
            class_name = obj.get('class', 'vehicle')
            track_id = obj.get('track_id', 0)
            
            color = colors.get(class_name, colors['vehicle'])
            
            # Ensure coordinates are valid
            if x2 > x1 and y2 > y1:
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label
                label = f"{class_name} ID:{track_id}"
                (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                
                # Ensure label fits in frame
                label_y = max(y1 - 5, label_h + 5)
                cv2.rectangle(frame, (x1, label_y - label_h - 5), (x1 + label_w, label_y), color, -1)
                cv2.putText(frame, label, (x1, label_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        return frame
    
    def _draw_detections(self, frame, detections):
        """Draw raw YOLO detections (fallback when tracking fails)"""
        import cv2
        
        colors = {
            'car': (0, 255, 255),
            'motorcycle': (0, 255, 0), 
            'bus': (255, 165, 0),
            'truck': (0, 0, 255),
            'vehicle': (255, 255, 255)
        }
        
        for detection in detections:
            bbox = detection['bbox']
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            class_name = detection.get('class', 'vehicle')
            confidence = detection.get('confidence', 0.0)
            
            color = colors.get(class_name, colors['vehicle'])
            
            if x2 > x1 and y2 > y1:
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"{class_name} {confidence:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return frame
    
    def start_detection(self):
        if not self.detection_running and self.detector and self.camera_manager:
            self.detection_running = True
            self.detection_thread = threading.Thread(target=self.detection_loop, daemon=True)
            self.detection_thread.start()
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.status_var.set("Detection started")
        elif not self.detector or not self.camera_manager:
            self.status_var.set("Components not ready")
    
    def stop_detection(self):
        if self.detection_running:
            self.detection_running = False
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.status_var.set("Detection stopped")
    
    def detection_loop(self):
        while self.detection_running:
            try:
                # Create a copy of camera keys to avoid "dictionary changed size during iteration"
                camera_ids = list(self.camera_manager.cameras.keys())
                for cam_id in camera_ids:
                    if cam_id not in self.camera_manager.cameras:
                        continue  # Camera was removed during iteration
                    
                    camera_data = self.camera_manager.cameras[cam_id]
                    if not camera_data['frame_queue'].empty():
                        frame = camera_data['frame_queue'].get()
                        
                        detections = self.detector.detect_vehicles(frame)
                        print(f"[DEBUG] YOLO detections: {len(detections)}")

                        # Initialize tracker if not exists
                        if cam_id not in self.trackers:
                            self.trackers[cam_id] = Tracker()

                        # Update tracker with detections
                        try:
                            tracked_objects = self.trackers[cam_id].update(detections, frame)
                            print(f"[DEBUG] Tracker returned {len(tracked_objects)} objects")
                        except Exception as e:
                            print(f"[ERROR] Tracker failed: {e}")
                            tracked_objects = []

                        # Always draw something if we have detections
                        if tracked_objects:
                            frame = self._draw_bounding_boxes(frame, tracked_objects)
                            print(f"[DEBUG] Drew {len(tracked_objects)} tracked boxes")
                        elif detections:
                            frame = self._draw_detections(frame, detections)
                            print(f"[DEBUG] Drew {len(detections)} raw detections (tracker failed)")
                        else:
                            print("[DEBUG] No detections to draw")
                        
                        # License plate detection
                        if self.plate_detector and (tracked_objects or detections):
                            objects_to_check = tracked_objects if tracked_objects else detections
                            for obj in objects_to_check:
                                if 'bbox' in obj:
                                    plate_info = self.plate_detector.detect_plate(frame, obj['bbox'])
                                    if plate_info:
                                        # Draw plate on frame
                                        frame = draw_plate_detection(frame, plate_info)
                                        
                                        # Save to database
                                        plate_num = plate_info['plate_number']
                                        vehicle_type = obj.get('class', 'unknown')
                                        confidence = plate_info['confidence']
                                        
                                        # Avoid duplicate saves (check if recently detected)
                                        if cam_id not in self.recent_plates:
                                            self.recent_plates[cam_id] = []
                                        
                                        # Only save if not seen in last 5 seconds
                                        now = datetime.now()
                                        recent = [p for p, t in self.recent_plates[cam_id] 
                                                 if (now - t).seconds < 5]
                                        
                                        if plate_num not in recent:
                                            self.db_manager.save_plate_detection(
                                                cam_id, plate_num, vehicle_type, confidence
                                            )
                                            self.recent_plates[cam_id].append((plate_num, now))
                                            print(f"[PLATE] Detected: {plate_num} ({vehicle_type})")
                                        
                                        # Cleanup old entries
                                        self.recent_plates[cam_id] = [
                                            (p, t) for p, t in self.recent_plates[cam_id]
                                            if (now - t).seconds < 30
                                        ]
                        
                        # Process line counting
                        if cam_id in self.line_counters:
                            frame = self.line_counters[cam_id].update(tracked_objects, frame)
                        
                        # Add camera info to frame
                        info_text = f"{cam_id} - {datetime.now().strftime('%H:%M:%S')}"
                        cv2.putText(frame, info_text, (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                        
                        # Update display
                        self.root.after(0, lambda f=frame, cid=cam_id: self.update_camera_display(cid, f))
                        self.root.after(0, self.update_statistics)
                        
            except Exception as e:
                print(f"Detection error: {e}")
                if not self.detection_running:
                    break
    
    def update_camera_display(self, cam_id, frame):
        """Update camera display based on current view mode"""
        try:
            # Convert frame to PhotoImage
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_pil = Image.fromarray(frame_rgb)
            
            if self.view_mode == "single" and cam_id == self.current_camera:
                # Single view - use larger size
                # Get available space
                label_width = self.single_camera_label.winfo_width()
                label_height = self.single_camera_label.winfo_height()
                
                if label_width > 1 and label_height > 1:  # Ensure window is initialized
                    # Calculate size maintaining aspect ratio
                    aspect_ratio = frame.shape[1] / frame.shape[0]
                    
                    # Leave some padding
                    max_width = label_width - 20
                    max_height = label_height - 20
                    
                    if max_width / aspect_ratio <= max_height:
                        new_width = max_width
                        new_height = int(max_width / aspect_ratio)
                    else:
                        new_height = max_height
                        new_width = int(max_height * aspect_ratio)
                    
                    frame_pil = frame_pil.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    # Default size if window not ready
                    frame_pil = frame_pil.resize((960, 720), Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(frame_pil)
                self.single_camera_label.configure(image=photo, text="")
                self.single_camera_label.image = photo
                
            elif self.view_mode == "grid" and cam_id in self.camera_labels:
                # Grid view - smaller size
                frame_pil = frame_pil.resize((320, 240), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(frame_pil)
                self.camera_labels[cam_id].configure(image=photo, text="")
                self.camera_labels[cam_id].image = photo
                
        except Exception as e:
            print(f"Display error for {cam_id}: {e}")


    def update_statistics(self):
        """Update vehicle count statistics (thread-safe)"""
        try:
            # Aggregate counts from all line counters
            total_counts = {'Mobil': 0, 'Motor': 0, 'Bus': 0, 'Truk': 0}
            
            for counter in self.line_counters.values():
                if hasattr(counter, 'total_counts'):
                    for vehicle_type, count in counter.total_counts.items():
                        if vehicle_type in total_counts:
                            total_counts[vehicle_type] += count
            
            # Update UI labels
            class_mapping = {'car': 'Mobil', 'motorcycle': 'Motor', 'bus': 'Bus', 'truck': 'Truk'}
            for ui_key, display_name in class_mapping.items():
                if ui_key in self.stats_labels:
                    self.stats_labels[ui_key].configure(text=str(total_counts[display_name]))
                    
        except Exception as e:
            print(f"[ERROR] Statistics update failed: {e}")
    
    def load_date_data(self):
        date_str = self.date_var.get()
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            summaries = self.db_manager.get_daily_summary(date)
            
            total_counts = defaultdict(int)
            
            for summary in summaries:
                total_counts['car'] += summary.cars
                total_counts['motorcycle'] += summary.motorcycles
                total_counts['bus'] += summary.buses
                total_counts['truck'] += summary.trucks
            
            for vehicle_type, label in self.stats_labels.items():
                label.configure(text=str(total_counts[vehicle_type]))
            
            self.status_var.set(f"Loaded data for {date_str}")
                
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD")
    
    def export_csv(self):
        date_str = self.date_var.get()
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            filepath = self.db_manager.export_to_csv(date)
            messagebox.showinfo("Success", f"Data exported to {filepath}")
            self.status_var.set(f"Exported to {filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")
    
    def run(self):
        # Set up window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Update window on resize
        self.root.bind("<Configure>", self.on_window_resize)
        
        self.root.mainloop()
    
    def on_window_resize(self, event=None):
        """Handle window resize to adjust camera display"""
        if self.view_mode == "single" and self.current_camera:
            # Force redraw with new size
            pass  # The next frame update will handle the resize
    
    def on_closing(self):
        """Clean up when closing the application"""
        # Stop detection first
        self.stop_detection()
        
        # Stop all camera threads
        for cam_id in list(self.camera_manager.cameras.keys()):
            self.camera_manager.remove_camera(cam_id)
        
        # Close database connection
        self.db_manager.close()
        
        self.root.destroy()


# Additional helper dialog for camera settings
class CameraSettingsDialog:
    def __init__(self, parent, camera_id, line_counter):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Settings - {camera_id}")
        self.dialog.geometry("400x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.line_counter = line_counter
        self.camera_id = camera_id
        
        # Line position setting
        ttk.Label(self.dialog, text="Detection Line Position:", 
                 font=("Arial", 12)).grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        self.line_scale = ttk.Scale(self.dialog, from_=0.1, to=0.9, 
                                   orient=tk.HORIZONTAL, length=200)
        self.line_scale.set(self.line_counter.line_position)
        self.line_scale.grid(row=0, column=1, padx=15, pady=15)
        
        # Line position value label
        self.line_value = ttk.Label(self.dialog, text=f"{self.line_counter.line_position:.0%}")
        self.line_value.grid(row=0, column=2, padx=15, pady=15)
        
        # Update label when scale moves
        self.line_scale.configure(command=self.update_line_value)
        
        # Detection zones (future feature)
        zones_frame = ttk.LabelFrame(self.dialog, text="Detection Zones", padding="10")
        zones_frame.grid(row=1, column=0, columnspan=3, padx=15, pady=15, sticky="ew")
        
        ttk.Label(zones_frame, text="Coming soon: Define custom detection zones", 
                 font=("Arial", 10), foreground="gray").pack()
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.grid(row=2, column=0, columnspan=3, pady=20)
        
        ttk.Button(button_frame, text="Apply", 
                  command=self.apply_settings).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Cancel", 
                  command=self.dialog.destroy).pack(side=tk.LEFT, padx=10)
    
    def update_line_value(self, value):
        self.line_value.configure(text=f"{float(value):.0%}")
    
    def apply_settings(self):
        self.line_counter.line_position = self.line_scale.get()
        self.dialog.destroy()


# Run the application
if __name__ == "__main__":
    app = TrafficDashboard()
    app.run()
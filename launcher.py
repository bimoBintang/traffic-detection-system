#!/usr/bin/env python3
"""
Simplified launcher for EXE build
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading

# Add current directory to path for imports
if hasattr(sys, '_MEIPASS'):
    # Running as EXE
    os.chdir(sys._MEIPASS)

class TrafficDetectionLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Traffic Detection System")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        self.service = None
        self.setup_ui()
    
    def setup_ui(self):
        # Title
        title = tk.Label(self.root, text="Traffic Detection System", 
                        font=("Arial", 16, "bold"))
        title.pack(pady=20)
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        status_label = tk.Label(self.root, textvariable=self.status_var)
        status_label.pack(pady=10)
        
        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=20)
        
        self.start_btn = tk.Button(btn_frame, text="Start Detection", 
                                  command=self.start_detection, 
                                  bg="green", fg="white", width=15)
        self.start_btn.pack(pady=5)
        
        self.stop_btn = tk.Button(btn_frame, text="Stop Detection", 
                                 command=self.stop_detection, 
                                 bg="red", fg="white", width=15, state="disabled")
        self.stop_btn.pack(pady=5)
        
        # Stats
        self.stats_text = tk.Text(self.root, height=8, width=50)
        self.stats_text.pack(pady=10, padx=20, fill="both", expand=True)
        
        # Update stats periodically
        self.update_stats()
    
    def start_detection(self):
        try:
            from detector import TrafficDetectionService
            self.service = TrafficDetectionService()
            self.service.start()
            
            self.status_var.set("Detection Running...")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start detection: {e}")
    
    def stop_detection(self):
        if self.service:
            self.service.stop()
            self.service = None
        
        self.status_var.set("Detection Stopped")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
    
    def update_stats(self):
        if self.service:
            try:
                stats = self.service.get_stats()
                stats_text = f"""Detection Statistics:
Total Detections: {stats.get('total_detections', 0)}
Running: {stats.get('running', False)}
Queue Size: {stats.get('queue_size', 0)}
Unsynced Records: {stats.get('unsynced_count', 0)}

Status: {'Active' if stats.get('running') else 'Stopped'}
"""
                self.stats_text.delete(1.0, tk.END)
                self.stats_text.insert(1.0, stats_text)
            except:
                pass
        
        self.root.after(2000, self.update_stats)  # Update every 2 seconds
    
    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()
    
    def on_closing(self):
        if self.service:
            self.stop_detection()
        self.root.destroy()

if __name__ == "__main__":
    app = TrafficDetectionLauncher()
    app.run()

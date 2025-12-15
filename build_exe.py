#!/usr/bin/env python3
"""
Build script to create EXE from traffic detection system
"""
import os
import sys
import subprocess
import shutil

def install_pyinstaller():
    """Install PyInstaller if not present"""
    try:
        import PyInstaller
        print("✅ PyInstaller already installed")
    except ImportError:
        print("📦 Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def check_files():
    """Check required files exist"""
    required_files = [
        "main.py",
        "detector.py", 
        "yolov8n.pt",
        "videoplayback.mp4",
        "database/fb-credentials.json"
    ]
    
    missing = []
    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)
    
    if missing:
        print(f"❌ Missing files: {missing}")
        return False
    
    print("✅ All required files present")
    return True

def build_exe():
    """Build the EXE using PyInstaller"""
    print("🔨 Building EXE...")
    
    # Clean previous builds
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")
    
    # Build command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--windowed",
        "--name=TrafficDetection",
        "--add-data=yolov8n.pt;.",
        "--add-data=videoplayback.mp4;.",
        "--add-data=database/fb-credentials.json;database/",
        "--hidden-import=ultralytics",
        "--hidden-import=torch",
        "--hidden-import=cv2",
        "--hidden-import=firebase_admin",
        "--hidden-import=sqlalchemy",
        "--hidden-import=tkinter",
        "main.py"
    ]
    
    try:
        subprocess.check_call(cmd)
        print("✅ EXE built successfully!")
        print("📁 Output: dist/TrafficDetection.exe")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        return False

def build_simple():
    """Simple build without spec file"""
    print("🔨 Building simple EXE...")
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--console",
        "--name=TrafficDetection",
        "run_detection.py"
    ]
    
    try:
        subprocess.check_call(cmd)
        print("✅ Simple EXE built!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Simple build failed: {e}")
        return False

def main():
    print("Traffic Detection System - EXE Builder")
    print("=" * 40)
    
    # Install PyInstaller
    install_pyinstaller()
    
    # Check files
    if not check_files():
        print("Please ensure all required files are present")
        return
    
    print("\nBuild options:")
    print("1. Full build (with GUI)")
    print("2. Simple build (console)")
    print("3. Custom spec file")
    
    choice = input("Choose option (1-3): ").strip()
    
    if choice == "1":
        success = build_exe()
    elif choice == "2":
        success = build_simple()
    elif choice == "3":
        if os.path.exists("traffic_detection.spec"):
            try:
                subprocess.check_call(["pyinstaller", "traffic_detection.spec"])
                success = True
            except subprocess.CalledProcessError:
                success = False
        else:
            print("❌ Spec file not found")
            success = False
    else:
        print("Invalid choice")
        return
    
    if success:
        print("\n🎉 Build completed!")
        print("📁 Check the 'dist' folder for your EXE file")
        
        # Show file size
        exe_path = "dist/TrafficDetection.exe"
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"📊 EXE size: {size_mb:.1f} MB")

if __name__ == "__main__":
    main()

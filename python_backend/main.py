import os
import sys
import threading
import time
import json
import socket
import cv2
import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from urllib.parse import urlparse

# Add the current directory to sys.path to import from backend_cctv
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging

# ── WRITABLE STORAGE PATHS ──────────────────────────────────────────────────
# We use the user's home directory to ensure we have write permissions on Windows
STORAGE_DIR = os.path.join(os.path.expanduser("~"), ".ceova")
os.makedirs(STORAGE_DIR, exist_ok=True)

LOG_FILE = os.path.join(STORAGE_DIR, "backend.log")
CAMERAS_FILE = os.path.join(STORAGE_DIR, "cameras.json")

# Configure logging to use the writable path
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("UnifiedBackend")
logger.info("Backend process starting...")

# Global State for Scanning
is_scanning = False
scan_progress = 0
found_cameras = []

try:
    from backend_cctv.stream_manager import StreamManager
    from backend_cctv.tracker import PersonTracker
    from backend_cctv.config import API_HOST, API_PORT
    logger.info("Modules imported successfully")
except Exception as e:
    logger.error(f"Failed to import modules: {e}")
    sys.exit(1)

def build_rtsp(ip, username=None, password=None, path="/cam/realmonitor?channel=1&subtype=0"):
    """Guarantees a perfectly formatted RTSP URL. Sanitizes all inputs."""
    if not ip:
        return None
        
    # 1. Sanitize
    ip = str(ip).strip()
    u = str(username).strip() if username else None
    p = str(password).strip() if password else None
    
    # 2. Build Auth (Strict Encoding for symbols like @)
    auth = ""
    from urllib.parse import quote
    if u and p:
        auth = f"{quote(u, safe='')}:{quote(p, safe='')}@"
    elif u:
        auth = f"{quote(u, safe='')}@"
        
    # 3. Ensure Port
    host = ip
    if ":" not in ip:
        host = f"{ip}:554"
        
    # 4. Final Construction
    url = f"rtsp://{auth}{host}{path}"
    logger.info(f"Generated Safe RTSP: {url}")
    return url

# Optimize for Mac (M1)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

app = FastAPI(title="Ceova CCTV Unified Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CAMERAS_FILE = os.path.join(os.path.dirname(__file__), "cameras.json")
managers = {} # cid -> StreamManager
trackers = {} # cid -> PersonTracker
active_threads = {} # cid -> bool
scanning_status = {"progress": 0, "total": 255, "found": []}

SUPABASE_URL = "https://jqpbgcmrlpfqnellznhz.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpxcGJnY21ybHBmcW5lbGx6bmh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIxMDkyMjcsImV4cCI6MjA4NzY4NTIyN30.rFHThZwo-caz0vFUUCoBeNFlUsTlOHqiQY_ds9vTwzw"

current_session = {
    "authenticated": False,
    "user_id": None,
    "email": None
}

def verify_supabase_token(token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": SUPABASE_ANON_KEY
    }
    response = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

@app.post("/init")
def init_session(data: dict):
    token = data.get("access_token")
    if not token:
        return Response(content=json.dumps({"error": "Unauthorized"}), status_code=401, media_type="application/json")
    
    user_data = verify_supabase_token(token)
    if user_data:
        current_session["authenticated"] = True
        current_session["user_id"] = user_data.get("id")
        current_session["email"] = user_data.get("email")
        return {"success": True, "user_id": current_session["user_id"]}
    else:
        current_session["authenticated"] = False
        current_session["user_id"] = None
        current_session["email"] = None
        return Response(content=json.dumps({"error": "Unauthorized"}), status_code=401, media_type="application/json")

@app.get("/session-status")
def session_status():
    return {
        "authenticated": current_session["authenticated"],
        "email": current_session["email"]
    }

@app.get("/status")
def status():
    return {"status": "online"}

def load_cameras():
    if os.path.exists(CAMERAS_FILE):
        try:
            with open(CAMERAS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading cameras: {e}")
    return {}

def save_cameras(cameras):
    try:
        with open(CAMERAS_FILE, "w") as f:
            json.dump(cameras, f)
    except Exception as e:
        print(f"Error saving cameras: {e}")

@app.get("/auto-discover")
def auto_discover():
    """Detects local subnet to help user find cameras"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except:
        local_ip = "192.168.1.1"
    finally:
        s.close()
    subnet = ".".join(local_ip.split(".")[:-1])
    return {"subnet": subnet, "local_ip": local_ip}

@app.get("/scan-progress")
def get_scan_progress():
    return scanning_status

def run_deep_scan(subnet, username, password, priority_ips):
    global scanning_status
    logger.info(f"Universal Pro Scan Started for subnet: {subnet}")
    found_cameras = []
    lock = threading.Lock()

    def check_ip(ip):
        # 1. Expanded Port Check
        ports = [554, 8554, 8000, 8899, 80, 8080, 81]
        open_port = None
        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.05) # Super fast check
                    if s.connect_ex((ip, port)) == 0:
                        open_port = port
                        break
            except: pass
        
        if open_port is None:
            with lock: scanning_status["progress"] += 1
            return False

        # 2. Universal Path Coverage
        paths = [
            "/cam/realmonitor?channel=1&subtype=0", 
            "/Streaming/Channels/101", 
            "/stream1", "/11", "/live/ch0",
            "/onvif/device_service", "/media/video1",
            "/video.mp4", "/h264_vga.sdp", "/live.sdp"
        ]
        
        for path in paths:
            url = f"rtsp://{username}:{password}@{ip}:{open_port}{path}"
            # Quick check if it's a valid RTSP stream
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 800) # 0.8s timeout
            if cap.isOpened():
                ret, _ = cap.read()
                cap.release()
                if ret:
                    with lock:
                        cam = {"ip": ip, "url": url, "name": f"Camera {ip.split('.')[-1]}"}
                        if not any(c["ip"] == ip for c in found_cameras):
                            found_cameras.append(cam)
                            scanning_status["found"].append(cam)
                    return True
        
        with lock: scanning_status["progress"] += 1
        return False

    import concurrent.futures
    all_ips = priority_ips + [f"{subnet}.{i}" for i in range(1, 255) if f"{subnet}.{i}" not in priority_ips]
    scanning_status["total"] = len(all_ips)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        executor.map(check_ip, all_ips)

    scanning_status["progress"] = scanning_status["total"]
    logger.info(f"Pro Scan finished. Found {len(found_cameras)} cameras.")

def run_deep_scan(username, password):
    global scanning_status
    found_cameras = []
    lock = threading.Lock()

    subnets = ["192.168.1", "192.168.0", "10.0.0"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        current_subnet = ".".join(local_ip.split(".")[:-1])
        if current_subnet not in subnets: subnets.insert(0, current_subnet)
    except: pass

    def check_ip(ip):
        # 1. Expanded Deep Port Check
        ports = [554, 37777, 34567, 80, 81, 8000, 8554, 8899, 8080, 8081, 9000]
        open_port = None
        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.06)
                    if s.connect_ex((ip, port)) == 0:
                        open_port = port
                        break
            except: pass
        
        if open_port is None:
            with lock: scanning_status["progress"] += 1
            return False

        # --- SMART PORT DIVERT ---
        # If we found the web port (80/81), cameras usually stream on 554
        video_port = open_port
        if open_port in [80, 81, 8080, 8081]:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.05)
                    if s.connect_ex((ip, 554)) == 0: video_port = 554
            except: pass

        # 2. INSTANT REPORT
        with lock:
            cam_name = f"Camera {ip.split('.')[-1]}"
            if not any(c["ip"] == ip for c in found_cameras):
                placeholder_url = build_rtsp(f"{ip}:{video_port}", username, password)
                cam = {"ip": ip, "url": placeholder_url, "name": cam_name, "status": "checking"}
                found_cameras.append(cam)
                scanning_status["found"].append(cam)
                logger.info(f"Potential camera discovered at {ip}:{video_port}")

        # 3. BACKGROUND VERIFY & PERMANENT SAVE
        from urllib.parse import quote
        u = quote(username) if username else ""
        p = quote(password) if password else ""
        auth = f"{u}:{p}@" if u else ""

        paths = ["/cam/realmonitor?channel=1&subtype=0", "/Streaming/Channels/101", "/stream1", "/live/ch0", "/onvif/device_service", "/video.mp4"]
        for path in paths:
            url = build_rtsp(f"{ip}:{video_port}", username, password, path)
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500)
            if cap.isOpened():
                with lock:
                    for c in scanning_status["found"]:
                        if c["ip"] == ip: 
                            c["url"] = url
                            c["status"] = "verified"
                            # SAVE PERMANENTLY
                            cid = f"cam_{ip.replace('.', '_')}"
                            cameras[cid] = {"name": c["name"], "rtsp_url": url, "ip": ip}
                            save_cameras(cameras)
                cap.release()
                break
        
        with lock: scanning_status["progress"] += 1
        return True

    all_ips = []
    for sub in subnets: all_ips += [f"{sub}.{i}" for i in range(1, 255)]
    
    return {"progress": scanning_status, "is_scanning": is_scanning, "found": found_cameras}

def scan_worker(ip, username, password):
    """Turbo-charged worker for parallel scanning"""
    global found_cameras
    
    # Very aggressive timeout for scanning phase
    url = build_rtsp(ip, username, password)
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500) 
    
    if cap.isOpened():
        ret, _ = cap.read()
        if ret:
            logger.info(f"TURBO-SCAN: Found camera at {ip}")
            cid = f"cam_{ip.replace('.', '_')}"
            found_cameras.append({
                "ip": ip,
                "name": f"Camera {ip.split('.')[-1]}",
                "url": url,
                "status": "verified"
            })
    cap.release()

@app.post("/scan-network")
def scan_network(data: dict):
    global is_scanning, scan_progress, found_cameras
    if is_scanning: return {"status": "already_scanning"}
    
    username = data.get("username", "admin")
    password = data.get("password", "")
    subnet = data.get("subnet", "192.168.1")
    
    is_scanning = True
    scan_progress = 0
    found_cameras = []
    
    def run_scan():
        global scan_progress, is_scanning
        ips = [f"{subnet}.{i}" for i in range(1, 255)]
        total = len(ips)
        
        logger.info(f"Starting Turbo-Scan on {subnet}.0/24...")
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            future_to_ip = {executor.submit(scan_worker, ip, username, password): ip for ip in ips}
            done_count = 0
            for future in concurrent.futures.as_completed(future_to_ip):
                done_count += 1
                scan_progress = int((done_count / total) * 100)
        
        is_scanning = False
        logger.info(f"Turbo-Scan complete. Found {len(found_cameras)} cameras.")

    threading.Thread(target=run_scan, daemon=True).start()
    return {"status": "scan_started"}

@app.get("/cameras")
def get_cameras():
    return load_cameras()

@app.get("/camera-status/{cid}")
def camera_status(cid: str):
    """Check if a camera is actively streaming frames"""
    if cid in managers:
        mgr = managers[cid]
        frame = mgr.get_frame() if hasattr(mgr, 'get_frame') else None
        if frame is not None:
            return {"status": "streaming"}
        else:
            return {"status": "connecting"}
    
    # Camera not in managers - check why
    cameras = load_cameras()
    if cid not in cameras:
        return {"status": "not_found"}
    
    cam = cameras[cid]
    rtsp_url = cam.get("rtsp_url", "")
    
    # Quick socket check
    try:
        parsed = urlparse(rtsp_url)
        host = parsed.hostname
        port = parsed.port or 554
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex((host, port)) != 0:
                return {"status": "offline", "reason": "Camera unreachable on network"}
    except:
        return {"status": "offline", "reason": "Invalid camera URL"}
    
    # Port is open but not streaming - likely wrong password
    return {"status": "wrong_credentials", "reason": "Camera found but credentials rejected (401)"}

def build_rtsp(ip, username=None, password=None, path="/cam/realmonitor?channel=1&subtype=0", encode=True):
    """Guarantees a perfectly formatted RTSP URL. Handles special chars in passwords."""
    if not ip: return None
    
    ip = str(ip).strip()
    u = str(username).strip() if username else None
    p = str(password).strip() if password else None
    
    from urllib.parse import quote
    auth = ""
    if u and p:
        if encode:
            # Encoded version for FFMPEG stability
            auth = f"{quote(u, safe='')}:{quote(p, safe='')}@"
        else:
            # Raw version for cameras that don't decode %40
            auth = f"{u}:{p}@"
    elif u:
        auth = f"{quote(u, safe='')}@"
        
    host = ip if ":" in ip else f"{ip}:554"
    return f"rtsp://{auth}{host}{path}"

@app.post("/verify-login")
def verify_login(data: dict):
    username = data.get("username", "admin")
    password = data.get("password", "")
    target_ip = data.get("ip", "192.168.1.245")
    
    # Try Encoded first (Most stable)
    for use_encoding in [True, False]:
        url = build_rtsp(target_ip, username, password, encode=use_encoding)
        if not url: continue
            
        logger.info(f"Deep-verifying (encoded={use_encoding}) for {target_ip}...")
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000) # 15 seconds timeout
        
        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            if ret:
                logger.info(f"Deep-verification SUCCESS (encoded={use_encoding})")
                
                # --- NVR AUTO-POPULATE ---
                cameras = load_cameras()
                
                # 1. Save Primary Camera (Channel 1)
                cid_1 = f"cam_{target_ip.replace('.', '_')}"
                cameras[cid_1] = {
                    "id": cid_1,
                    "name": "Camera 1",
                    "rtsp_url": url,
                    "ip": target_ip
                }
                
                # 2. Find other channels
                if "/cam/realmonitor" in url:
                    for ch in range(2, 9):
                        ch_path = f"/cam/realmonitor?channel={ch}&subtype=0"
                        ch_url = build_rtsp(target_ip, username, password, path=ch_path, encode=use_encoding)
                        c = cv2.VideoCapture(ch_url, cv2.CAP_FFMPEG)
                        c.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1000)
                        if c.isOpened():
                            r, _ = c.read()
                            if r:
                                cid = f"cam_{target_ip.replace('.', '_')}_{ch}"
                                cameras[cid] = {
                                    "id": cid,
                                    "name": f"Camera {ch}",
                                    "rtsp_url": ch_url,
                                    "ip": target_ip
                                }
                                logger.info(f"Auto-added Channel {ch}: {ch_url}")
                        c.release()
                    save_cameras(cameras)
                
                return {"success": True}
        else:
            cap.release()

    logger.warning(f"Deep-verification FAILED for {target_ip}")
    return {"success": False, "error": "Unauthorized: Invalid credentials or camera timeout"}

def auto_detect_rtsp(ip, username, password):
    from urllib.parse import quote
    u = quote(username) if username else ""
    p = quote(password) if password else ""
    
    # We always want to test both unauthenticated and authenticated versions
    # Because some cameras have authentication disabled or don't require it for certain streams
    patterns_to_test = []
    
    common_ports = [554, 8554, 8000, 8899]
    base_paths = [
        "/cam/realmonitor?channel=1&subtype=0",
        "/Streaming/Channels/101",
        "/stream1",
        "/live"
    ]
    
    patterns_to_test = []
    
    for port in common_ports:
        # Build host with port
        host = f"{ip}:{port}"
        
        # Add patterns without auth and with auth
        for path in base_paths:
            # No Auth
            patterns_to_test.append(build_rtsp(host, None, None, path))
            # With Auth
            if username:
                patterns_to_test.append(build_rtsp(host, username, password, path))

    working_urls = []
    for url in patterns_to_test:
        if not url: continue
        logger.info(f"Auto-detecting RTSP for {ip}: trying {url}")
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000)
        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            if ret:
                logger.info(f"RTSP Auto-detect SUCCESS: {url}")
                working_urls.append(url)
                
                # --- NVR CHANNEL PROBE ---
                # If this is a realmonitor URL, it's likely an NVR. Let's find other channels!
                if "realmonitor" in url:
                    base_url = url.split("?")[0]
                    for ch in range(2, 9): # Check channels 2 to 8
                        ch_url = f"{base_url}?channel={ch}&subtype=0"
                        c = cv2.VideoCapture(ch_url, cv2.CAP_FFMPEG)
                        c.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1000)
                        if c.isOpened():
                            r, _ = c.read()
                            c.release()
                            if r:
                                logger.info(f"NVR Channel {ch} discovered: {ch_url}")
                                working_urls.append(ch_url)
                        else:
                            c.release()
                
                # If we found any, we stop searching other base patterns (stream1/live etc)
                return working_urls
        else:
            cap.release()
            
    return working_urls

@app.post("/add-camera")
def add_camera(data: dict):
    cid_base = data.get("id", "cam")
    name_base = data.get("name", "Camera")
    ip = data.get("ip")
    username = data.get("username", "")
    password = data.get("password", "")
    rtsp = data.get("rtsp")
    
    working_urls = [rtsp] if rtsp else []
    if not working_urls and ip:
        working_urls = auto_detect_rtsp(ip, username, password)
        
    if not working_urls:
        raise HTTPException(status_code=400, detail="Camera not reachable or wrong credentials")
    
    cameras = load_cameras()
    for i, url in enumerate(working_urls):
        cid = f"{cid_base}_{i+1}" if len(working_urls) > 1 else cid_base
        name = f"{name_base} {i+1}" if len(working_urls) > 1 else name_base
        cameras[cid] = {
            "id": cid,
            "name": name,
            "rtsp_url": url,
            "ip": ip or "Unknown"
        }
    
    save_cameras(cameras)
    return {"success": True, "count": len(working_urls)}

@app.delete("/remove-camera/{cid}")
def remove_camera(cid: str):
    cameras = load_cameras()
    if cid in cameras:
        del cameras[cid]
        save_cameras(cameras)
        if cid in managers:
            managers[cid].stop()
            del managers[cid]
    return {"success": True}

@app.post("/test-stream")
def test_stream(data: dict):
    rtsp_url = data.get("rtsp_url")
    if not rtsp_url:
        return {"success": False, "error": "No URL"}
    
    # 1. Fast Socket Pre-check
    try:
        from urllib.parse import urlparse
        # Handle rtsp://user:pass@ip:port/path
        if "@" in rtsp_url:
            host_part = rtsp_url.split("@")[1].split("/")[0]
        else:
            host_part = rtsp_url.split("//")[1].split("/")[0]
        
        if ":" in host_part:
            host, port = host_part.split(":")
            port = int(port)
        else:
            host, port = host_part, 554
            
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) != 0:
                return {"success": False, "error": "Port closed"}
    except:
        pass # Fallback to VideoCapture if parsing fails

    # 2. Optimized VideoCapture
    # Use 2s timeout for FFMPEG
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp;timeout=2000000"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if cap.isOpened():
        ret, _ = cap.read()
        cap.release()
        if ret:
            return {"success": True}
        else:
            return {"success": False, "error": "Stream found but could not read"}
            
    # Check if it was a 401 specifically (optional but helpful)
    # OpenCV doesn't always expose the HTTP code easily, but we can infer from logs if needed.
    # For now, let's just make sure the UI knows it failed.
    return {"success": False, "error": "Unreachable or Wrong Credentials"}

def camera_process_loop(cid, rtsp_url):
    """Connects to RTSP and runs the StreamManager capture loop with optional AI overlay."""
    tracker = None
    try:
        tracker = PersonTracker()
    except Exception as e:
        logger.warning(f"AI tracking disabled for {cid}: {e}")
    
    cameras = load_cameras()
    cam = cameras.get(cid)
    if not cam: return
    
    url = cam.get("rtsp_url")
    
    # Final 'Double-At' Cleanse: If the URL has @84@... it's malformed
    if "@84@" in url:
        logger.warning(f"Malformed URL detected in cache, sanitizing: {url}")
        url = url.replace("@84@", "@")
        
    logger.info(f"Starting process loop for {cid}: {url}")
    
    manager = StreamManager(rtsp_url=url)
    if not manager.connect():
        logger.error(f"Failed to connect to stream: {url}")
        return

    manager.start()  # Starts the internal capture thread in StreamManager
    managers[cid] = manager
    active_threads[cid] = True
    
    # This loop ONLY handles AI overlays, not frame capture.
    # Frame capture is done in StreamManager._update() on its own thread.
    # Optimization: Only run AI every X frames to keep FPS high
    frame_count = 0
    while active_threads.get(cid):
        if tracker is None:
            # No AI: clear processed buffer so we fall back to raw
            manager.last_processed_frame = None
            time.sleep(0.1)
            continue

        frame = manager.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue
        
        frame_count += 1
        try:
            # ONLY RUN AI ON EVERY 3rd FRAME TO BOOST FPS
            if frame_count % 3 == 0:
                tracks = tracker.update(frame)
                frame = tracker.draw_tracks(frame, tracks)
            
            # Encode quickly (Quality 75 for speed)
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            manager.last_processed_frame = buffer.tobytes()
        except Exception as e:
            logger.warning(f"AI error on {cid}: {e}")
            tracker = None  # Disable on error
            
        time.sleep(0.001) # Near zero wait

    manager.stop()
    print(f"Stopped loop for {cid}")

@app.post("/start/{cid}")
def start_camera(cid: str):
    cameras = load_cameras()
    if cid not in cameras:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    rtsp_url = cameras[cid]["rtsp_url"]
    
    # Check if camera is already running with the SAME URL
    if cid in managers and cid in active_threads and active_threads[cid]:
        if managers[cid].rtsp_url == rtsp_url:
            logger.info(f"Camera {cid} already running, skipping restart.")
            return {"message": "Already running"}

    # Force restart if it's a new URL or not running
    if cid in active_threads: active_threads[cid] = False
    if cid in managers:
        try: managers[cid].stop()
        except: pass
        del managers[cid]
    
    time.sleep(0.2)
    thread = threading.Thread(target=camera_process_loop, args=(cid, rtsp_url), daemon=True)
    thread.start()
    return {"message": "Started"}

@app.post("/stop/{cid}")
def stop_camera(cid: str):
    if cid in active_threads:
        active_threads[cid] = False
    if cid in managers:
        managers[cid].stop()
    return {"message": "Stopped"}

@app.get("/stream/{cid}")
def stream_video(cid: str):
    if cid not in managers:
        cameras = load_cameras()
        if cid in cameras:
            start_camera(cid)
            time.sleep(1.5)  # Give stream time to connect
        else:
            raise HTTPException(status_code=404, detail="Stream not found")

    def generate():
        while active_threads.get(cid):
            mgr = managers.get(cid)
            if mgr is None:
                time.sleep(0.1)
                continue

            # Prefer AI-processed frame; fall back to raw frame
            frame_bytes = getattr(mgr, 'last_processed_frame', None)
            
            if frame_bytes is None:
                # No AI active — encode the raw frame directly
                raw = mgr.get_frame()
                if raw is not None:
                    _, buf = cv2.imencode('.jpg', raw, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_bytes = buf.tobytes()

            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            # Ultra-low latency: check for new frames every 10ms
            time.sleep(0.01)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    import uvicorn
    # 1. Start any existing cameras from JSON
    cameras = load_cameras()
    logger.info(f"Loaded {len(cameras)} cameras from file.")
    for cid, cam in cameras.items():
        logger.info(f"Auto-starting {cam['name']} at {cam['ip']}")
        threading.Thread(target=camera_process_loop, args=(cid, cam["rtsp_url"]), daemon=True).start()
        
    # 2. Run server on 0.0.0.0 for maximum compatibility
    uvicorn.run(app, host="0.0.0.0", port=8085)
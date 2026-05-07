import cv2
import time
import math

# ── Lazy AI loading ───────────────────────────────────────────────────────────
# torch and ultralytics are only imported when a camera requests AI detection.
# This allows the app to start and stream cameras with NO AI libraries installed.
_model = None

def _get_model():
    """Load YOLO model on first use only."""
    global _model
    if _model is None:
        try:
            import torch
            from ultralytics import YOLO
            import os
            # Find yolov8n.pt next to this file
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yolov8n.pt")
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            _model = YOLO(model_path).to(device)
        except Exception:
            _model = None  # AI unavailable — stream still works
    return _model

class HumanTracker:
    def __init__(self, timeout=3.0, dist_threshold=100):
        self.tracked_objects = {}  # {track_id: {"centroid": (x, y), "last_seen": timestamp, "user_id": "user1"}}
        self.user_counter = 0
        self.timeout = timeout
        self.dist_threshold = dist_threshold

    def update(self, detections):
        """
        detections: list of [x1, y1, x2, y2]
        """
        current_time = time.time()
        new_tracked_objects = {}
        
        # Calculate centroids for current detections
        current_detections = []
        for det in detections:
            x1, y1, x2, y2 = det
            centroid = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            current_detections.append({"bbox": det, "centroid": centroid})

        # Match current detections to existing tracked objects
        for det_info in current_detections:
            det_centroid = det_info["centroid"]
            best_match_id = None
            min_dist = self.dist_threshold

            for track_id, track_info in self.tracked_objects.items():
                dist = math.hypot(det_centroid[0] - track_info["centroid"][0], 
                                  det_centroid[1] - track_info["centroid"][1])
                if dist < min_dist:
                    min_dist = dist
                    best_match_id = track_id

            if best_match_id is not None:
                # Update existing track
                user_label = self.tracked_objects[best_match_id]["user_id"]
                new_tracked_objects[best_match_id] = {
                    "centroid": det_centroid,
                    "bbox": det_info["bbox"],
                    "last_seen": current_time,
                    "user_id": user_label
                }
                # Remove from old state to avoid multiple matching
                del self.tracked_objects[best_match_id]
            else:
                # New person detected
                self.user_counter += 1
                new_id = f"track_{current_time}_{self.user_counter}"
                new_tracked_objects[new_id] = {
                    "centroid": det_centroid,
                    "bbox": det_info["bbox"],
                    "last_seen": current_time,
                    "user_id": f"user{self.user_counter}"
                }

        # Keep existing tracks that weren't matched but haven't timed out
        for track_id, track_info in self.tracked_objects.items():
            if current_time - track_info["last_seen"] < self.timeout:
                new_tracked_objects[track_id] = track_info

        self.tracked_objects = new_tracked_objects
        return self.tracked_objects

# Global state for movement detection
motion_detectors = {}

def track_persons(frame, camera_id="1"):
    """
    Eagle Eyes AI: Tracks humans and ALL movement (Optimized).
    """
    if camera_id not in trackers:
        trackers[camera_id] = HumanTracker()
    
    # Initialize motion detector for this camera if needed
    if camera_id not in motion_detectors:
        motion_detectors[camera_id] = cv2.createBackgroundSubtractorMOG2(history=30, varThreshold=50, detectShadows=False)

    # --- ENGINE 1: MOVEMENT DETECTION (Optimized Slim Blue Boxes) ---
    # Downscale for performance
    small_frame = cv2.resize(frame, (400, int(400 * frame.shape[0] / frame.shape[1])))
    fg_mask = motion_detectors[camera_id].apply(small_frame)
    _, fg_mask = cv2.threshold(fg_mask, 240, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    scale_x = frame.shape[1] / 400
    scale_y = frame.shape[0] / (400 * frame.shape[0] / frame.shape[1])

    for cnt in contours:
        if cv2.contourArea(cnt) > 100: 
            mx, my, mw, mh = cv2.boundingRect(cnt)
            # Rescale back to original frame size
            rx, ry, rw, rh = int(mx * scale_x), int(my * scale_y), int(mw * scale_x), int(mh * scale_y)
            cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (255, 150, 0), 1)

    # --- ENGINE 2: HUMAN INTELLIGENCE (Green Slim Boxes + ID) ---
    # Only run if AI model is available (skipped gracefully on Windows without torch)
    model = _get_model()
    if model is not None:
        results = model.predict(frame, classes=[0], verbose=False, conf=0.15, agnostic_nms=True)
        
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append([x1, y1, x2, y2])

        tracked_people = trackers[camera_id].update(detections)

        for track_id, info in tracked_people.items():
            if time.time() - info["last_seen"] < 0.5:
                x1, y1, x2, y2 = map(int, info["bbox"])
                raw_id = info["user_id"].replace("user", "")
                id_label = f"ID:{raw_id}"

                # Green Slim Line for Humans
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 1)
                cv2.putText(frame, id_label, (x1, y1 - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    return frame

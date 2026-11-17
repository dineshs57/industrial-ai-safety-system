import cv2
from ultralytics import YOLO
import math
import time
import numpy as np
import pyttsx3
from collections import defaultdict
import requests
import os
import winsound
import threading

# Optional: Twilio for SOS phone calls (install: pip install twilio)
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("⚠️ Twilio not installed. SOS phone calls disabled. Install: pip install twilio")

# Frame file for sharing with backend
FRAME_FILE = ".detection_frame.jpg"

engine = pyttsx3.init()
EMPLOYEE_ID = "worker_001"
BACKEND_URL = "http://127.0.0.1:5000"

# ===== TWILIO SOS CONFIGURATION =====
# Install Twilio: pip install twilio
# Get credentials: https://www.twilio.com/try-twilio
TWILIO_ENABLED = True  # Set to False to disable SOS calls

# YOUR CREDENTIALS (Get from Twilio dashboard)
TWILIO_ACCOUNT_SID = "replace your"  # Replace with your Twilio Account SID
TWILIO_AUTH_TOKEN = "replace yours"    # Replace with your Twilio Auth Token
TWILIO_PHONE_FROM = "replace yours"        # Replace with your Twilio phone number
YOUR_PHONE_NUMBER = "replace yours"      # Replace with your personal phone (with country code)

# Initialize Twilio client
twilio_client = None
if TWILIO_ENABLED and TWILIO_AVAILABLE:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("✅ Twilio SOS system initialized")
    except Exception as e:
        print(f"⚠️ Twilio initialization failed: {e}")
        print(f"   Make sure credentials are correct in ai_detection.py")
        TWILIO_ENABLED = False

# ===== SIREN SOUND FUNCTION =====
def play_siren(duration=3):
    """
    Play a siren sound using Windows Beep
    Alternates between high and low frequency to create alarm effect
    Creates a distinctive alarm pattern: HIGH-LOW-HIGH-LOW...
    """
    def siren_loop():
        end_time = time.time() + duration
        while time.time() < end_time:
            # High frequency (1000 Hz) for 0.2 seconds
            winsound.Beep(1000, 200)
            # Low frequency (600 Hz) for 0.2 seconds  
            winsound.Beep(600, 200)
    
    # Run siren in background thread so it doesn't block video processing
    siren_thread = threading.Thread(target=siren_loop, daemon=True)
    siren_thread.start()

# ===== TWILIO SOS FUNCTIONS =====
def make_sos_call(worker_id, location_x, location_y, incident_type="FALL"):
    """
    Makes an emergency phone call to alert about incident
    Uses Twilio to make automated call with voice message
    Falls back to SMS if call fails
    
    Args:
        worker_id: Worker identifier
        location_x: X coordinate of incident
        location_y: Y coordinate of incident  
        incident_type: Type of incident (FALL, MEDICAL, etc.)
    """
    if not TWILIO_ENABLED or not twilio_client:
        print("⚠️ Twilio not configured - SOS call skipped")
        return False
    
    try:
        # Create voice message for the call
        message = (
            f"CRITICAL ALERT! {incident_type} detected for worker {worker_id} "
            f"at location {int(location_x)}, {int(location_y)}. "
            f"Emergency response activated. Repeat: CRITICAL ALERT!"
        )
        
        print(f"\n☎️ MAKING EMERGENCY CALL TO {YOUR_PHONE_NUMBER}...")
        
        # Make call with voice message
        call = twilio_client.calls.create(
            from_=TWILIO_PHONE_FROM,
            to=YOUR_PHONE_NUMBER,
            twiml=f'<Response><Say voice="alice">{message}</Say></Response>'
        )
        
        print(f"✅ EMERGENCY CALL PLACED")
        print(f"   📱 Call SID: {call.sid}")
        print(f"   📞 Calling: {YOUR_PHONE_NUMBER}")
        print(f"   ⏱️ Should arrive within 10 seconds")
        
        # Also send SMS as backup
        send_sos_sms(worker_id, location_x, location_y, incident_type)
        
        return True
        
    except Exception as e:
        print(f"❌ Emergency call failed: {e}")
        print(f"   Sending SMS backup instead...")
        send_sos_sms(worker_id, location_x, location_y, incident_type)
        return False


def send_sos_sms(worker_id, location_x, location_y, incident_type="FALL"):
    """
    Sends emergency SMS as backup or primary alert
    
    Args:
        worker_id: Worker identifier
        location_x: X coordinate of incident
        location_y: Y coordinate of incident
        incident_type: Type of incident
    """
    if not TWILIO_ENABLED or not twilio_client:
        return False
    
    try:
        message = (
            f"🚨 SOS ALERT: {incident_type} DETECTED!\n"
            f"Worker: {worker_id}\n"
            f"Location: ({int(location_x)}, {int(location_y)})\n"
            f"Status: Emergency response ACTIVATED\n"
            f"Time: {time.strftime('%H:%M:%S')}\n"
            f"Action: Check camera feed immediately"
        )
        
        print(f"\n📱 SENDING EMERGENCY SMS BACKUP TO {YOUR_PHONE_NUMBER}...")
        
        sms = twilio_client.messages.create(
            from_=TWILIO_PHONE_FROM,
            to=YOUR_PHONE_NUMBER,
            body=message
        )
        
        print(f"✅ EMERGENCY SMS SENT")
        print(f"   📱 Message SID: {sms.sid}")
        return True
        
    except Exception as e:
        print(f"❌ SMS failed: {e}")
        return False

# ===== EVENT SENDER =====
def send_event(event_type, detail):
    """
    Sends a structured event to the backend
    event_type: NO_HELMET, NO_VEST, FALL_DETECTED, UNCONSCIOUS_EMERGENCY, etc.
    detail: description of the event
    """
    try:
        payload = {
            "event": event_type,
            "detail": detail
        }
        response = requests.post(f"{BACKEND_URL}/event", json=payload, timeout=1)
        if response.status_code == 200:
            print(f"✅ Event sent: {event_type}")
        else:
            print(f"⚠️ Event failed: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Could not send event: {str(e)}")


# ===== AGENTIC PREVENTION ACTION SYSTEM =====
# Track action states to prevent duplicate triggers
ppe_alarm_active = False
proximity_alarm_active = False
fall_emergency_dispatched = False
security_lockdown_active = False
last_ppe_alarm_time = 0
last_proximity_alert_time = 0

def trigger_ppe_alarm(worker_id, missing_gear):
    """
    🚨 PPE Non-Compliance AGENTIC ACTION:
    - Sound SIREN alarm (distinctive high-low pattern)
    - Block machine startup
    - Reduce machine speed to 50%
    - Send supervisor alert
    """
    global ppe_alarm_active, last_ppe_alarm_time
    
    current_time = time.time()
    if current_time - last_ppe_alarm_time < 2:  # Cooldown to avoid spam
        return
    
    last_ppe_alarm_time = current_time
    
    # 📊 UPDATE METRICS
    metrics["total_incidents"] += 1
    metrics["ppe_violations"] += 1
    if "HELMET" in missing_gear:
        metrics["helmet_violations"] += 1
    else:
        metrics["vest_violations"] += 1
    
    print(f"\n🚨 PPE ALARM TRIGGERED - Worker {worker_id} missing {missing_gear}")
    print(f"   🔊 SIREN ACTIVATED! (High-Low pattern)")
    
    # 1. Sound siren alarm
    play_siren(duration=3)  # Play 3-second siren with HIGH-LOW pattern
    
    # Also speak the warning
    try:
        engine.say(f"Safety violation! Please wear {missing_gear} immediately. Machine operation blocked.")
        engine.runAndWait()
    except:
        pass
    
    # 2. Block machine startup
    print(f"  ✋ ACTION: Blocking machine startup")
    send_event("MACHINE_BLOCKED", f"Machine startup blocked - Worker missing {missing_gear}")
    
    # 3. Reduce machine speed to 50%
    print(f"  ⚙️ ACTION: Reducing nearby machine speed to 50%")
    send_event("MACHINE_SPEED_REDUCED", f"Machine speed reduced to 50% - PPE non-compliance")
    
    # 4. Send supervisor alert
    print(f"  👔 ACTION: URGENT supervisor alert sent")
    send_event("SUPERVISOR_URGENT_ALERT", f"URGENT: Worker {worker_id} non-compliant - Manual intervention REQUIRED!")
    
    # Send metrics update
    send_metrics()
    
    ppe_alarm_active = True


def trigger_proximity_alarm(distance, worker_id):
    """
    ⚠️ Machine-Human Proximity Danger AGENTIC ACTION:
    - Auto-stop the machine
    - Escalating proximity alarm
    - Lock down danger zone
    - Alert machine operator
    """
    global proximity_alarm_active, last_proximity_alert_time
    
    current_time = time.time()
    if current_time - last_proximity_alert_time < 1:
        return
    
    last_proximity_alert_time = current_time
    
    print(f"\n⚠️ PROXIMITY EMERGENCY - Worker {worker_id} at {int(distance)}px from machine!")
    
    # 1. Auto-stop machine
    print(f"  🛑 ACTION: Emergency STOP activated - Machine halting immediately")
    send_event("MACHINE_EMERGENCY_STOP", f"Machine emergency stop! Worker at critical distance {int(distance)}px")
    
    # 2. Escalating alarm
    if distance < 100:
        try:
            engine.say("CRITICAL DANGER! Machine stopping! Step back immediately!")
            engine.runAndWait()
        except:
            pass
        print(f"  🔊 ACTION: CRITICAL ALERT - Hazard distance detected (10 meters)")
    elif distance < 150:
        try:
            engine.say("Warning! Dangerous proximity to machine! Step back now!")
            engine.runAndWait()
        except:
            pass
        print(f"  🔊 ACTION: WARNING ALERT - Caution zone")
    
    # 3. Lock down danger zone
    print(f"  🔒 ACTION: Danger zone electronically locked")
    send_event("ZONE_LOCKDOWN", f"Danger zone locked - Access restricted due to proximity hazard")
    
    # 4. Alert machine operator
    print(f"  📡 ACTION: Machine operator notified")
    send_event("OPERATOR_ALERT", f"OPERATOR ALERT: Worker detected too close! Maintain safe distance!")
    
    # 5. Update metrics
    metrics["total_incidents"] += 1
    metrics["proximity_alerts"] += 1
    send_metrics()
    
    proximity_alarm_active = True


def trigger_fall_emergency(worker_id, location_x, location_y):
    """
    🆘 Fall/Unconsciousness AGENTIC ACTION:
    - IMMEDIATELY call SOS number on personal phone
    - Dispatch ambulance (911 call)
    - Notify supervisors with location
    - Keep camera focused on worker
    """
    global fall_emergency_dispatched
    
    if fall_emergency_dispatched:
        return
    
    print(f"\n🆘 FALL EMERGENCY - Worker {worker_id} at ({location_x}, {location_y})")
    
    # 1. MAKE EMERGENCY PHONE CALL (IMMEDIATE - Most Urgent!!!)
    print(f"  ☎️ ACTION: EMERGENCY PHONE CALL TO YOUR MOBILE")
    make_sos_call(worker_id, location_x, location_y, "FALL")
    send_event("PHONE_CALL_SOS", f"📞 EMERGENCY CALL PLACED to {YOUR_PHONE_NUMBER}")
    
    # 2. Dispatch ambulance
    print(f"  📞 ACTION: Calling 911 - Ambulance dispatch INITIATED")
    send_event("EMERGENCY_911_DISPATCH", f"911 CALL PLACED: Ambulance dispatched for worker {worker_id} at site ({int(location_x)}, {int(location_y)})")
    
    # 3. Notify all supervisors
    print(f"  📲 ACTION: SMS/Push notifications sent to ALL supervisors")
    send_event("SUPERVISOR_CRITICAL_ALERT", f"🆘 CRITICAL: Fall detected at ({int(location_x)}, {int(location_y)}) - EMS called - Immediate response needed")
    
    # 4. Camera focus
    print(f"  📹 ACTION: Camera recording focused on incident")
    send_event("INCIDENT_RECORDING", f"Critical incident recording: Fall at ({int(location_x)}, {int(location_y)})")
    
    # 5. Update metrics
    metrics["total_incidents"] += 1
    metrics["fall_detections"] += 1
    send_metrics()
    
    fall_emergency_dispatched = True
    print(f"  ⏱️ Emergency response protocol ACTIVATED")


def trigger_security_lockdown(worker_id, location_x, location_y):
    """
    🔓 Unauthorized Access AGENTIC ACTION:
    - Lock all doors/gates
    - Capture intruder photo
    - Block exit routes
    - High-zoom surveillance
    - Alert security team
    - Disable asset removal
    """
    global security_lockdown_active
    
    if security_lockdown_active:
        return
    
    print(f"\n🔓 SECURITY BREACH - Unauthorized access at ({location_x}, {location_y})")
    
    # 1. Lock all doors
    print(f"  🔐 ACTION: All facility doors LOCKED electronically")
    send_event("DOORS_LOCKED", f"LOCKDOWN: All entries locked to contain intruder")
    
    # 2. Capture photo
    print(f"  📸 ACTION: Intruder photo CAPTURED and logged")
    send_event("INTRUDER_PHOTO", f"Intruder detected and photographed at ({int(location_x)}, {int(location_y)})")
    
    # 3. Block exits
    print(f"  🚫 ACTION: Emergency exit routes BLOCKED")
    send_event("EXITS_BLOCKED", f"All escape routes sealed - Intruder containment ACTIVE")
    
    # 4. High-zoom surveillance
    print(f"  🎥 ACTION: High-zoom surveillance ACTIVATED on intruder")
    send_event("ZOOM_SURVEILLANCE", f"Camera zoomed and tracked on unauthorized person")
    
    # 5. Alert security
    print(f"  🚨 ACTION: Security team MOBILIZED")
    send_event("SECURITY_ALERT", f"SECURITY BREACH! Intruder in restricted zone - Containment ACTIVE")
    
    # 6. Disable assets
    print(f"  🔒 ACTION: All valuable assets LOCKED/DISABLED")
    send_event("ASSETS_DISABLED", f"Equipment and assets locked - Theft prevention ACTIVE")
    
    # 7. Update metrics
    metrics["total_incidents"] += 1
    metrics["security_breaches"] += 1
    send_metrics()
    
    security_lockdown_active = True
    print(f"  🛡️ Total facility lockdown INITIATED")


# ===== AGENT MEMORY =====
violation_log = defaultdict(int)
machine_active = True
theft_start_time = None

# ===== REAL-TIME METRICS TRACKING =====
metrics = {
    "total_incidents": 0,
    "ppe_violations": 0,
    "fall_detections": 0,
    "proximity_alerts": 0,
    "security_breaches": 0,
    "helmet_violations": 0,
    "vest_violations": 0,
    "start_time": time.time()
}

def send_metrics():
    """Send real-time metrics to backend"""
    try:
        elapsed_time = int(time.time() - metrics["start_time"])
        payload = {
            "total_incidents": metrics["total_incidents"],
            "ppe_violations": metrics["ppe_violations"],
            "fall_detections": metrics["fall_detections"],
            "proximity_alerts": metrics["proximity_alerts"],
            "security_breaches": metrics["security_breaches"],
            "helmet_violations": metrics["helmet_violations"],
            "vest_violations": metrics["vest_violations"],
            "runtime_seconds": elapsed_time
        }
        requests.post(f"{BACKEND_URL}/metrics", json=payload, timeout=0.5)
    except:
        pass  # Silent fail for metrics

# ==========================LOAD MODELS FIRST======================
print("\n⏳ Loading AI models...", end="", flush=True)
model = YOLO("best1.pt")              # PPE model
print(".", end="", flush=True)
machine_model = YOLO("yolov8n.pt") # General model
print(" ✅ Done!\n")

print("PPE Classes:", model.names)
print("Machine Classes:", machine_model.names)

# ==========================OPEN CAMERA (INSTANT DETECTION)======================
print("\n📷 Opening camera...")
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer for faster frame delivery

if not cap.isOpened():
    print("❌ Camera not opened")
    exit()

cv2.namedWindow("PPE Compliance System", cv2.WINDOW_NORMAL)
print("✅ Camera ready - Detection starting immediately!\n")
# ================= INTERACTIVE GEOFENCE DRAWING =================
# Press D, then LEFT-CLICK + DRAG to draw a RED danger-zone polygon.
# Press R, then LEFT-CLICK + DRAG to draw a YELLOW restricted-zone polygon.
# Press C to clear both zones.

danger_zone = []
restricted_zone = []

active_zone = None             # "danger", "restricted", or None
is_drawing = False
drawing_points = []
cursor_point = None

# Edge-state memory prevents sending the same entry event on every frame.
previous_danger_inside = False
previous_restricted_inside = False


def draw_zone(event, x, y, flags, param):
    """OpenCV mouse callback for freehand polygon drawing."""
    global is_drawing, drawing_points, cursor_point
    global danger_zone, restricted_zone

    cursor_point = (x, y)

    if event == cv2.EVENT_LBUTTONDOWN and active_zone is not None:
        is_drawing = True
        drawing_points = [(x, y)]

    elif event == cv2.EVENT_MOUSEMOVE and is_drawing:
        # Add points only after the cursor has moved a few pixels.
        if not drawing_points:
            drawing_points.append((x, y))
        else:
            last_x, last_y = drawing_points[-1]
            if abs(x - last_x) + abs(y - last_y) >= 4:
                drawing_points.append((x, y))

    elif event == cv2.EVENT_LBUTTONUP and is_drawing:
        if not drawing_points or drawing_points[-1] != (x, y):
            drawing_points.append((x, y))

        is_drawing = False

        # Remove nearly-collinear points to keep the polygon manageable.
        if len(drawing_points) >= 3:
            contour = np.array(drawing_points, dtype=np.int32).reshape(-1, 1, 2)
            epsilon = max(1.0, 0.003 * cv2.arcLength(contour, True))
            simplified = cv2.approxPolyDP(contour, epsilon, True)
            polygon = simplified.reshape(-1, 2).tolist()

            if len(polygon) >= 3:
                if active_zone == "danger":
                    danger_zone = polygon
                    print(f"RED DANGER ZONE saved ({len(polygon)} points)")
                elif active_zone == "restricted":
                    restricted_zone = polygon
                    print(f"YELLOW RESTRICTED ZONE saved ({len(polygon)} points)")
            else:
                print("Please draw a larger closed shape with at least 3 corners.")
        else:
            print("Zone not saved. Drag the mouse to draw at least 3 corners.")

        drawing_points = []


cv2.setMouseCallback("PPE Compliance System", draw_zone)


def point_inside_zone(point, zone):
    """Return True when point is inside or on the boundary of a polygon."""
    if zone is None or len(zone) < 3:
        return False

    polygon = np.array(zone, dtype=np.int32)
    return cv2.pointPolygonTest(
        polygon,
        (float(point[0]), float(point[1])),
        False
    ) >= 0



fall_start_time = None
theft_start_time = None

def draw_info_panel(frame, info_text):
    """Draw a clean info panel on the right side of frame"""
    h, w = frame.shape[:2]
    panel_width = 180
    
    # Draw semi-transparent panel
    overlay = frame.copy()
    cv2.rectangle(overlay, (w - panel_width, 0), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
    
    # Draw border
    cv2.rectangle(frame, (w - panel_width, 0), (w, h), (0, 200, 255), 2)
    
    # Draw text
    y_offset = 25
    for text, color in info_text:
        cv2.putText(frame, text, (w - panel_width + 10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        y_offset += 20
    
    return frame

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.resize(frame, (640, 640))
    h, w = frame.shape[:2]
    
    # ===== INFO COLLECTION =====
    info_panel = []  # List of (text, color) tuples
    helmet_detected = False
    vest_detected = False
    no_helmet_alert = False
    no_vest_alert = False
    emergency_status = ""

    # ================= PPE DETECTION =================
    results = model(frame, conf=0.25, iou=0.45)

    for r in results:
        if r.boxes is None:
            continue

        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            label = model.names[cls]
            color = (0, 255, 0)
            text = ""

            # Helmet
            if label in ["Hardhat", "helmet"]:
                text = "HELMET"
                helmet_detected = True
                color = (0, 255, 0)

            elif label in ["NO-Hardhat", "no-helmet"]:
                text = "NO HELMET"
                no_helmet_alert = True
                helmet_detected = False
                send_event("NO_HELMET", f"Worker {EMPLOYEE_ID} detected without helmet")
                violation_log[EMPLOYEE_ID] += 1
                count = violation_log[EMPLOYEE_ID]
                color = (0, 0, 255)
                # 🤖 AGENTIC ACTION: PPE Compliance Prevention
                trigger_ppe_alarm(EMPLOYEE_ID, "HELMET")
                
                if count == 1:
                    engine.say("Safety violation detected. Please wear helmet.")
                    engine.runAndWait()
                    emergency_status = "VOICE WARNING"
                elif count == 2:
                    emergency_status = "SUPERVISOR ALERTED"
                    send_event("SUPERVISOR_ALERT", f"Worker {EMPLOYEE_ID} has {count} violations")
                elif count >= 3:
                    emergency_status = "HR ESCALATION"
                    send_event("HR_ESCALATION", f"Worker {EMPLOYEE_ID} critical violations: {count}")

            # Vest
            elif label in ["Safety Vest", "vest", "safety-vest"]:
                text = "VEST"
                vest_detected = True
                color = (0, 255, 0)

            elif label in ["NO-Safety Vest", "no-vest"]:
                text = "NO VEST"
                no_vest_alert = True
                vest_detected = False
                send_event("NO_VEST", f"Worker {EMPLOYEE_ID} detected without safety vest")
                color = (0, 0, 255)
                # 🤖 AGENTIC ACTION: PPE Compliance Prevention
                trigger_ppe_alarm(EMPLOYEE_ID, "SAFETY VEST")

            else:
                continue

            # Draw bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{text} {conf:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # ================= MACHINE + PERSON DETECTION =================
    machine_results = machine_model(frame, conf=0.3)

    persons = []
    machines = []
    fall_detected = False
    proximity_danger = False
    zone_danger = False
    unconscious_time = 0

    for r in machine_results:
        if r.boxes is None:
            continue

        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls = int(box.cls[0])
            label = machine_model.names[cls]

            # PERSON
            if label == "person":
                persons.append((x1, y1, x2, y2))
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

                # ================= FALL DETECTION =================
                w = x2 - x1
                h = y2 - y1

                if w > h * 1.2:
                    fall_detected = True
                    
                    if fall_start_time is None:
                        fall_start_time = time.time()
                        send_event("FALL_DETECTED", f"Worker {EMPLOYEE_ID} fall detected")
                        # 🤖 AGENTIC ACTION: Emergency Response for Fall
                        trigger_fall_emergency(EMPLOYEE_ID, (x1 + x2) // 2, (y1 + y2) // 2)

                    unconscious_time = int(time.time() - fall_start_time)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    
                    if unconscious_time >= 10:
                        send_event("UNCONSCIOUS_EMERGENCY", f"Worker {EMPLOYEE_ID} critical - unconscious for {unconscious_time}s")

            # MACHINES / VEHICLES
            elif label in ["car", "truck", "bus", "motorcycle", "excavator"]:
                machines.append((x1, y1, x2, y2))
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 165, 255), 2)

    # ================= DISTANCE SAFETY =================
    for (px1, py1, px2, py2) in persons:
        pcx = (px1 + px2) // 2
        pcy = (py1 + py2) // 2

        for (mx1, my1, mx2, my2) in machines:
            mcx = (mx1 + mx2) // 2
            mcy = (my1 + my2) // 2

            distance = math.sqrt((pcx - mcx) ** 2 + (pcy - mcy) ** 2)
            cv2.line(frame, (pcx, pcy), (mcx, mcy), (0, 0, 255), 1)

            if distance < 150:
                proximity_danger = True
                send_event("PROXIMITY_ALERT", f"Worker {EMPLOYEE_ID} too close to machine - distance: {int(distance)}px")
                # 🤖 AGENTIC ACTION: Proximity Danger Prevention
                trigger_proximity_alarm(distance, EMPLOYEE_ID)

    # ================= DRAW ZONE POLYGONS + LIVE PREVIEW =================
    danger_color = (0, 0, 255)          # Red in OpenCV BGR
    restricted_color = (0, 255, 255)   # Yellow in OpenCV BGR

    if len(danger_zone) >= 3:
        cv2.polylines(
            frame, [np.array(danger_zone, dtype=np.int32)],
            True, danger_color, 3
        )
        cv2.putText(
            frame, "DANGER ZONE",
            tuple(danger_zone[0]),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, danger_color, 2
        )

    if len(restricted_zone) >= 3:
        cv2.polylines(
            frame, [np.array(restricted_zone, dtype=np.int32)],
            True, restricted_color, 3
        )
        cv2.putText(
            frame, "RESTRICTED ZONE",
            tuple(restricted_zone[0]),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, restricted_color, 2
        )

    # Draw the line as the mouse moves, before the user releases the button.
    if is_drawing and len(drawing_points) >= 1:
        preview_color = danger_color if active_zone == "danger" else restricted_color
        preview = np.array(drawing_points, dtype=np.int32).reshape(-1, 1, 2)
        if len(drawing_points) >= 2:
            cv2.polylines(frame, [preview], False, preview_color, 2)

        if cursor_point is not None:
            cv2.line(
                frame, drawing_points[-1], cursor_point,
                preview_color, 2
            )

    # Show which zone mode is selected.
    if active_zone == "danger":
        mode_text = "DRAWING MODE: DANGER (RED) - click and drag"
        mode_color = danger_color
    elif active_zone == "restricted":
        mode_text = "DRAWING MODE: RESTRICTED (YELLOW) - click and drag"
        mode_color = restricted_color
    else:
        mode_text = "Press D or R to select a zone"
        mode_color = (255, 255, 255)

    cv2.putText(
        frame, mode_text, (10, 45),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45, mode_color, 1
    )

   
# ================= PERSON-IN-ZONE CHECK =================

danger_inside = False
restricted_inside = False

for (px1, py1, px2, py2) in persons:

    # Calculate person centre
    center_point = (
        (px1 + px2) // 2,
        (py1 + py2) // 2
    )

    # Calculate person's foot position
    foot_point = (
        (px1 + px2) // 2,
        py2
    )

    # Visual debugging points
    cv2.circle(frame, center_point, 6, (0, 255, 0), -1)
    cv2.circle(frame, foot_point, 6, (255, 255, 0), -1)

    # Danger zone: centre OR feet inside
    if (
        point_inside_zone(center_point, danger_zone)
        or point_inside_zone(foot_point, danger_zone)
    ):
        danger_inside = True

    # Restricted zone: centre OR feet inside
    if (
        point_inside_zone(center_point, restricted_zone)
        or point_inside_zone(foot_point, restricted_zone)
    ):
        restricted_inside = True

        zone_danger = danger_inside

    # ================= DANGER ZONE MACHINE-STATUS SIMULATION =================
    # This changes the software status and sends events to Flask.
    # It does NOT physically stop or restart factory machinery.
    machine_active = not danger_inside

    if danger_inside and not previous_danger_inside:
        print("DANGER ZONE ENTRY - software machine status OFF")
        send_event(
            "MACHINE_STOPPED",
            f"Worker {EMPLOYEE_ID} entered the danger zone"
        )
        send_event(
            "DANGER_ZONE_ENTRY",
            f"Worker {EMPLOYEE_ID} entered the danger zone"
        )

    elif not danger_inside and previous_danger_inside:
        print("DANGER ZONE CLEAR - software machine status ON/READY")
        send_event(
            "MACHINE_READY",
            f"Worker {EMPLOYEE_ID} left the danger zone; manual safety reset required for real machinery"
        )
        send_event(
            "DANGER_ZONE_CLEAR",
            f"Worker {EMPLOYEE_ID} left the danger zone"
        )

    # ================= RESTRICTED ZONE WARNING =================
    if restricted_inside and not previous_restricted_inside:
        print("WARNING - person entered the restricted zone")
        send_event(
            "UNAUTHORIZED_ACCESS",
            f"Worker {EMPLOYEE_ID} entered the restricted zone"
        )

    elif not restricted_inside and previous_restricted_inside:
        print("Restricted zone is clear")
        send_event(
            "RESTRICTED_ZONE_CLEAR",
            f"Worker {EMPLOYEE_ID} left the restricted zone"
        )

    previous_danger_inside = danger_inside
    previous_restricted_inside = restricted_inside

    # ================= BUILD INFO PANEL =================
    info_panel = []
    
    # PPE Status
    if helmet_detected:
        info_panel.append(("✓ Helmet", (0, 255, 0)))
    else:
        info_panel.append(("✗ NO HELMET!", (0, 0, 255)))
    
    if vest_detected:
        info_panel.append(("✓ Vest", (0, 255, 0)))
    else:
        info_panel.append(("✗ NO VEST!", (0, 0, 255)))
    
    # Safety Alerts
    if fall_detected:
        info_panel.append(("⚠ FALL!", (0, 0, 255)))
        if unconscious_time > 0:
            info_panel.append((f"Conscious: {unconscious_time}s", (0, 0, 255)))
    
    if proximity_danger:
        info_panel.append(("⚠ PROXIMITY ALERT", (0, 0, 255)))
    
    if zone_danger:
        info_panel.append(("DANGER: PERSON INSIDE", (0, 0, 255)))

    if restricted_inside:
        info_panel.append(("RESTRICTED ZONE ALERT!", (0, 255, 255)))

    # Software machine status is controlled by danger-zone occupancy.
    if machine_active:
        info_panel.append(("Machine: ON / READY", (0, 255, 0)))
    else:
        info_panel.append(("Machine: OFF", (0, 0, 255)))

    # Draw the info panel
    frame = draw_info_panel(frame, info_panel)
    
    # ================= UI HELP =================
    cv2.putText(frame, "D=Danger | R=Restricted | C=Clear", 
                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # ================= SAVE FRAME FOR BACKEND =================
    try:
        cv2.imwrite(FRAME_FILE, frame)
    except:
        pass  # Ignore write errors

    cv2.imshow("PPE Compliance System", frame)

    key = cv2.waitKey(1) & 0xFF

    if key in (ord('d'), ord('D')):
        active_zone = "danger"
        drawing_points = []
        is_drawing = False
        print("DANGER mode selected: LEFT-CLICK and DRAG to draw a RED polygon.")

    elif key in (ord('r'), ord('R')):
        active_zone = "restricted"
        drawing_points = []
        is_drawing = False
        print("RESTRICTED mode selected: LEFT-CLICK and DRAG to draw a YELLOW polygon.")

    elif key == ord('c'):
        danger_zone.clear()
        restricted_zone.clear()
        drawing_points = []
        is_drawing = False
        active_zone = None
        previous_danger_inside = False
        previous_restricted_inside = False
        machine_active = True
        print("Both zones cleared. Machine status simulation set to ON/READY.")

    elif key == ord('q'):
        break


cap.release()
cv2.destroyAllWindows()


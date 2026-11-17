# AI-Powered Smart Industrial Safety and Monitoring System Using Computer Vision

An edge AI computer vision and automated intervention system designed for industrial manufacturing and construction environments. The system performs real-time PPE compliance auditing, worker fall and unconsciousness detection, machine-worker proximity hazard monitoring, and virtual polygon geofencing with autonomous multi-tier escalation protocols.

---

## 📌 Key Features (Implemented)

### 1. Real-Time PPE Compliance Detection
- **Dual YOLOv8 Architecture**: Utilizes fine-tuned YOLOv8 models (`best1.pt` and `yolov8n.pt`) to detect safety gear (Helmets, Safety Vests, Gloves, Goggles, Masks, Safety Shoes).
- **Worker Audit Logging**: Automatically tracks non-compliance infractions mapped to individual worker IDs with structured severity logging.

### 2. Temporal Fall & Unconsciousness Detection
- **Aspect Ratio Analysis**: Dynamically monitors worker bounding box dimensions. A horizontal orientation ($width > 1.2 \times height$) initiates an incident timer.
- **Unconsciousness Escalation**: If a fall condition persists for $\ge 10\text{–}15\text{ seconds}$, the system flags an `UNCONSCIOUS_EMERGENCY`, triggers audible sirens, and dispatches emergency alert payloads.

### 3. Machine-Worker Proximity Monitoring
- **Euclidean Distance Tracking**: Computes real-time pixel distances between worker centroids and heavy machinery/vehicles (`car`, `truck`, `bus`, `motorcycle`, `excavator`).
- **Hazard Zones**:
  - Distance $< 150\text{px}$: Warning alert and visual indicator line.
  - Distance $< 100\text{px}$: Critical danger alert, acoustic warning, and automated machine halt event.

### 4. Interactive Polygon Geofencing
- **Virtual Boundary Definition**: Supports interactive drawing of **Danger Zones** (`D` key) and **Restricted Zones** (`R` key) directly on live video via OpenCV mouse callbacks.
- **Ray-Casting Algorithm**: Implements point-in-polygon testing against worker centroid and foot positions to detect perimeter breaches.
- **Machine Interlock Simulation**: Automatically triggers software machine shutdown (`MACHINE_STOPPED`) upon unauthorized zone entry.

### 5. Multi-Tier Autonomous Escalation (Agentic Protocol)
- **Acoustic & Voice Warnings**: On-device text-to-speech warnings (`pyttsx3`) and alternating dual-frequency emergency sirens (`winsound`).
- **Remote SOS Dispatch**: Integrated alerting capability (Twilio REST API / automated email dispatch) to notify safety administrators during critical falls or unauthorized intrusions.
- **Three-Strike Policy**: Escalates from local voice warning (Violation 1) $\to$ Supervisor alert (Violation 2) $\to$ HR/Admin escalation (Violation 3+).

### 6. Flask REST API & Video Streaming Backend
- **Live MJPEG Video Stream**: Streams processed frames with bounding boxes and HUD status overlays over HTTP (`GET /video`).
- **Event Queue**: In-memory circular buffer maintaining the latest 100 safety incidents (`GET /events`).
- **Worker Registry**: Tracks historical violation tallies per worker (`GET /violations/<worker_id>`).
- **Telemetry Metrics**: Aggregates real-time incident counters, violation breakdowns, and system uptime (`GET /metrics`).

---

## 🛠️ Tech Stack

- **Primary Language**: Python 3.8+
- **Computer Vision & AI**: Ultralytics YOLOv8, OpenCV (`cv2`), NumPy
- **Backend API**: Flask, Flask-CORS
- **Speech & Audio**: Pyttsx3, Winsound
- **Networking & Alerts**: Requests, RESTful APIs

---

## 📁 Repository Structure

```text
├── ai_detection.py           # Core CV pipeline, YOLO inference, geofencing & escalation
├── backend_server.py         # Flask REST API, circular event buffer & MJPEG stream
├── best1.pt                  # Trained YOLOv8 model weights for PPE detection
├── yolov8n.pt                # General YOLOv8 model for person and machine detection
├── requirements.txt          # Python dependencies
├── .gitignore                # Git ignore rules for virtual environments and cache
└── README.md                 # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites & Installation

Clone the repository and install the dependencies:
```bash
git clone https://github.com/dineshs57/<repo-name>.git
cd <repo-name>
pip install -r requirements.txt
```

### 2. Running the System

#### Step 1: Start the Backend Server
```bash
python backend_server.py
```
*Server starts at `http://127.0.0.1:5000`.*

#### Step 2: Launch AI Detection Engine
In a second terminal:
```bash
python ai_detection.py
```

### 3. Interactive Keyboard Controls
While the camera feed window is active:
- **`D`**: Switch to **Danger Zone** polygon drawing mode.
- **`R`**: Switch to **Restricted Zone** polygon drawing mode.
- **`C`**: Clear all drawn virtual zones.
- **`Q`**: Safely stop detection and close camera.

---

## 📡 API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/video` | `GET` | Live multipart MJPEG video stream with HUD overlays |
| `/event` | `POST` | Ingests structured safety incident payloads from detection engine |
| `/events` | `GET` | Retrieves recent events from the circular buffer (max 100) |
| `/violations/<worker_id>` | `GET` | Fetches historical safety violation logs for a specific worker |
| `/metrics` | `GET` | Returns aggregated metrics (total incidents, falls, runtime, etc.) |

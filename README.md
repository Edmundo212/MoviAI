# SmartFlow 🚦 — AI-powered adaptive traffic signals

**WFEO Hackathon 2027 · Challenge 3: Smart, Digital and Data-Driven Transport (SDG 9)**

SmartFlow analyses video from existing intersection cameras with **Azure AI Vision (Computer Vision – Image Analysis 4.0)**,
counts vehicles and pedestrians on each approach, and recommends optimal traffic-signal timings using **Webster's method**.
Its *people-first* mode weights each vehicle by its passengers, so a bus carrying 30 people gets priority over a car with one.

## How it works
1. **Capture** – a live public traffic camera (HLS/RTSP/MJPEG/JPEG), or a recorded video/photo of an intersection.
2. **Detect** – Azure AI Vision (`OBJECTS` + `PEOPLE`) finds cars, motorcycles, buses, trucks, bicycles and pedestrians.
3. **Count** – each detection is assigned to an approach zone (N, S, E, W), converted to PCU and to people.
4. **Optimise** – Webster's formula computes the optimal cycle and green split, with a safe pedestrian minimum green.
5. **Compare** – estimated average delay per vehicle and per person: fixed-time plan vs SmartFlow.

```
Video → OpenCV (1 frame / 3 s) → Azure AI Vision → zones → Webster → dashboard (Flask + Chart.js)
                                                        ↘ MongoDB / JSON storage
```

## Project structure
| Path | Description |
|---|---|
| `app.py` | Flask web app (upload, results, JSON API) |
| `smartflow/vision.py` | Azure AI Vision client, label mapping, rate limiting |
| `smartflow/zones.py` | Approach zones (polygons) and signal phases |
| `smartflow/webster.py` | Webster cycle / green split and delay estimation |
| `smartflow/processor.py` | Frame extraction, detection, counting, annotated images |
| `smartflow/live.py` | Live mode: grabs frames from public traffic cameras and updates the plan in real time |
| `cameras.json` | Preset public cameras (Caltrans) with their approach zones |
| `smartflow/storage.py` | MongoDB (if `MONGODB_URI` set) or local JSON |
| `deploy/` | Azure VM deployment guide, systemd and Nginx configs |

## Run locally
```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # then fill in VISION_ENDPOINT and VISION_KEY
python app.py                     # http://localhost:5000
```

## Deploy on Azure
See [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

## Configuration
- `.env` – Azure keys, MongoDB URI, sampling rate (see `.env.example`).
- `zones.json` – approach polygons matching your camera view (see `zones.example.json`).
- `smartflow/config.py` – label mapping, PCU factors and average occupancy per vehicle class.

## Privacy
Original videos are deleted after processing, only counts are stored, and faces are blurred in annotated frames.

## Known limitations
- The general Azure model does not know local vehicle types (e.g. *combis*, *mototaxis*); they are mapped to the closest class.
- In dense motorcycle traffic, many riders are detected as `person` but their motorcycles are not, so they may be counted as pedestrians.
- Azure Computer Vision's general model detects nearby vehicles well but misses small, tightly packed vehicles far from the camera (e.g. long queues on wide-angle traffic CCTV), so counts are a lower bound. Close-up camera angles give the best results.
- Flows are estimated from observed queues (snapshot counts), not from tracking individual vehicles.
- Future work: a custom-trained model for local vehicle types and an edge version for intersections with poor connectivity.

## Team
- Member 1 – Data & evaluation
- Member 2 – Development & Azure
- Member 3 – Engineering & communication

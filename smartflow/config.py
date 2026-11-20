"""Configuración central de SmartFlow (se lee desde variables de entorno / .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# En Linux, el OpenSSL que trae OpenCV no encuentra los certificados del sistema
# y falla al abrir streams HTTPS (cámaras en vivo). Le indicamos dónde están.
_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
if not os.getenv("SSL_CERT_FILE") and _CA_BUNDLE.exists():
    os.environ["SSL_CERT_FILE"] = str(_CA_BUNDLE)

# --- Azure AI Vision (Computer Vision - Image Analysis 4.0) ---
VISION_ENDPOINT = os.getenv("VISION_ENDPOINT", "")
VISION_KEY = os.getenv("VISION_KEY", "")
# Plan gratuito F0: ~20 llamadas/minuto -> 1 llamada cada 3.1 s
VISION_MIN_SECONDS_BETWEEN_CALLS = float(os.getenv("VISION_MIN_SECONDS_BETWEEN_CALLS", "3.1"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.5"))

# --- Detector local complementario (YOLOX-S, ONNX con OpenCV) ---
# Se usa JUNTO con Azure Computer Vision (no lo reemplaza): mejora la detección de vehículos
# pequeños o lejanos. LOCAL_DETECTOR=0 para usar solo Azure.
LOCAL_DETECTOR_ENABLED = os.getenv("LOCAL_DETECTOR", "1") not in ("0", "false", "no")
LOCAL_MODEL_PATH = BASE_DIR / "models" / "yolox_s.onnx"
LOCAL_MIN_CONFIDENCE = float(os.getenv("LOCAL_MIN_CONFIDENCE", "0.3"))
LOCAL_TILES = os.getenv("LOCAL_TILES", "1") not in ("0", "false", "no")   # recortes ampliados
# En vivo, las cajas del video se refrescan con YOLOX cada N segundos (sin gastar llamadas a Azure)
LIVE_LOCAL_REFRESH_SECONDS = float(os.getenv("LIVE_LOCAL_REFRESH_SECONDS", "1.0"))

# --- Base de datos ---
MONGODB_URI = os.getenv("MONGODB_URI", "")          # si está vacío se usa archivo JSON local
MONGODB_DB = os.getenv("MONGODB_DB", "smartflow")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "smartflow_analyses")
# Una medición por frame analizado (conteos + plan calculado)
MONGODB_MEASUREMENTS_COLLECTION = os.getenv("MONGODB_MEASUREMENTS_COLLECTION", "smartflow_measurements")

# --- Procesamiento de video ---
FRAME_INTERVAL_SECONDS = float(os.getenv("FRAME_INTERVAL_SECONDS", "3"))
MAX_FRAMES = int(os.getenv("MAX_FRAMES", "40"))
MAX_IMAGE_WIDTH = 1280

# --- Video en vivo fluido ---
# El video se transmite (MJPEG) a LIVE_FPS aunque Azure solo analice un frame cada N segundos;
# entre análisis las cajas siguen a los vehículos con flujo óptico (OpenCV, sin costo de API).
LIVE_FPS = float(os.getenv("LIVE_FPS", "15"))
LIVE_STREAM_WIDTH = int(os.getenv("LIVE_STREAM_WIDTH", "960"))
LIVE_JPEG_QUALITY = int(os.getenv("LIVE_JPEG_QUALITY", "75"))

# --- Carpetas ---
UPLOAD_DIR = BASE_DIR / "uploads"
RESULTS_DIR = BASE_DIR / "static" / "results"
DATA_DIR = BASE_DIR / "data"
ZONES_FILE = BASE_DIR / "zones.json"
for d in (UPLOAD_DIR, RESULTS_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Clases de vehículos ---
# Etiquetas que devuelve Azure (en minúsculas) -> clase de SmartFlow.
# Azure no conoce "combi" ni "mototaxi": suelen salir como van / car / motorcycle.
LABEL_MAP = {
    "car": "auto", "taxi": "auto", "land vehicle": "auto", "vehicle": "auto",
    "wheeled vehicle": "auto", "suv": "auto", "sedan": "auto", "minivan": "auto",
    "van": "bus", "minibus": "bus", "bus": "bus", "school bus": "bus",
    "truck": "camion", "pickup truck": "camion", "trailer truck": "camion",
    "motorcycle": "moto", "scooter": "moto", "motor scooter": "moto", "moped": "moto",
    "bicycle": "bicicleta",
    "person": "peaton",
}

# Unidades de auto equivalente (PCU) para el cálculo de ingeniería de tránsito.
PCU = {"auto": 1.0, "moto": 0.5, "bus": 3.0, "camion": 2.0, "bicicleta": 0.2}

# Ocupación promedio (personas por vehículo) para el modo "personas primero".
OCCUPANCY = {"auto": 1.5, "moto": 1.2, "bus": 30.0, "camion": 1.2, "bicicleta": 1.0}

# Colores para dibujar las cajas (BGR para OpenCV).
CLASS_COLORS = {
    "auto": (255, 170, 0), "moto": (0, 200, 255), "bus": (0, 220, 0),
    "camion": (180, 0, 255), "bicicleta": (255, 255, 0), "peaton": (60, 60, 255),
}

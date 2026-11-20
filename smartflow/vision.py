"""Cliente de Azure AI Vision (Image Analysis 4.0): detecta vehículos y personas."""
import threading
import time

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

from . import config

_client = None
_lock = threading.Lock()
_last_call = 0.0


def get_client() -> ImageAnalysisClient:
    global _client
    if _client is None:
        if not config.VISION_ENDPOINT or not config.VISION_KEY:
            raise RuntimeError("Faltan VISION_ENDPOINT / VISION_KEY en el archivo .env")
        _client = ImageAnalysisClient(config.VISION_ENDPOINT, AzureKeyCredential(config.VISION_KEY))
    return _client


def _wait_rate_limit():
    """Respeta el límite de llamadas por minuto del plan de Azure."""
    global _last_call
    with _lock:
        wait = config.VISION_MIN_SECONDS_BETWEEN_CALLS - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


def analyze_image(image_bytes: bytes, width: int, height: int, retries: int = 3) -> list[dict]:
    """Envía una imagen a Azure y devuelve detecciones normalizadas.

    Cada detección: {clase, etiqueta, confianza, x, y, w, h} (coordenadas en píxeles).
    """
    client = get_client()
    for attempt in range(retries):
        _wait_rate_limit()
        try:
            result = client.analyze(
                image_data=image_bytes,
                visual_features=[VisualFeatures.OBJECTS, VisualFeatures.PEOPLE],
            )
            break
        except HttpResponseError as e:
            if e.status_code == 429 and attempt < retries - 1:   # demasiadas llamadas
                time.sleep(10 * (attempt + 1))
                continue
            raise

    detections = []
    if result.objects:
        for obj in result.objects.list:
            tag = obj.tags[0]
            label = tag.name.lower()
            cls = config.LABEL_MAP.get(label)
            if cls is None or cls == "peaton":          # personas vienen de PEOPLE
                continue
            if tag.confidence < config.MIN_CONFIDENCE:
                continue
            b = obj.bounding_box
            detections.append({"clase": cls, "etiqueta": label, "confianza": round(tag.confidence, 3),
                               "x": b.x, "y": b.y, "w": b.width, "h": b.height})

    if result.people:
        for p in result.people.list:
            # PEOPLE devuelve muchas cajas con confianza baja: usamos un umbral mayor
            if p.confidence < max(config.MIN_CONFIDENCE, 0.6):
                continue
            b = p.bounding_box
            # descartamos personas dentro de un vehículo (caja contenida en la de un vehículo)
            if _inside_vehicle(b, detections):
                continue
            detections.append({"clase": "peaton", "etiqueta": "person", "confianza": round(p.confidence, 3),
                               "x": b.x, "y": b.y, "w": b.width, "h": b.height})
    return detections


def _inside_vehicle(b, detections) -> bool:
    cx, cy = b.x + b.width / 2, b.y + b.height / 2
    for d in detections:
        # incluye motos y bicicletas: así no contamos al conductor como peatón
        if d["clase"] != "peaton" and d["x"] <= cx <= d["x"] + d["w"] and d["y"] <= cy <= d["y"] + d["h"]:
            return True
    return False

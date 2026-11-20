"""Modo en vivo: toma frames de una cámara pública de tráfico (HLS, RTSP, MJPEG o JPEG),
los analiza con Azure Computer Vision y actualiza el plan de semáforo en tiempo real."""
import ipaddress
import json
import socket
import threading
import time
import traceback
import urllib.request
import uuid
from collections import deque
from urllib.parse import urlparse

import cv2
import numpy as np

from . import config, processor, webster, zones as zones_mod
from .storage import store, now_iso

CAMERAS_FILE = config.BASE_DIR / "cameras.json"
WINDOW = 12                 # el plan se calcula con los últimos 12 frames
MAX_CONSECUTIVE_ERRORS = 4
SESSIONS: dict[str, "LiveSession"] = {}


def load_cameras() -> list[dict]:
    if CAMERAS_FILE.exists():
        return json.loads(CAMERAS_FILE.read_text(encoding="utf-8")).get("cameras", [])
    return []


def get_camera(camera_id: str) -> dict | None:
    return next((c for c in load_cameras() if c["id"] == camera_id), None)


def validate_url(url: str):
    """Evita que el servidor acceda a direcciones internas (seguridad en la VM de Azure)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https", "rtsp") or not p.hostname:
        raise ValueError("The camera URL must start with http://, https:// or rtsp://")
    for info in socket.getaddrinfo(p.hostname, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Private or internal network addresses are not allowed.")


def grab_frame(url: str):
    path = urlparse(url).path.lower()
    if path.endswith((".jpg", ".jpeg", ".png")) or "snapshot" in path:
        req = urllib.request.Request(url, headers={"User-Agent": "SmartFlow/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read(15 * 1024 * 1024)
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    else:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG,
                               [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 20000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 20000])
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        cap.release()
        if not ok:
            frame = None
    if frame is None:
        raise RuntimeError("Could not read a frame from the camera.")
    return processor.resize(frame)


class LiveSession:
    def __init__(self, name, url, zones, phases, params, interval, duration_min, source=""):
        self.id = "live" + uuid.uuid4().hex[:8]
        self.name, self.url, self.source = name, url, source
        self.zones, self.phases, self.params = zones, phases, params
        self.interval = max(interval, config.VISION_MIN_SECONDS_BETWEEN_CALLS)
        self.duration = duration_min * 60
        self.window = deque(maxlen=WINDOW)
        self.all_records = []
        self.timeline = []
        self.state = "starting"
        self.error = None
        self.calls = 0
        self.started = time.time()
        self.stop_event = threading.Event()
        self.out_dir = config.RESULTS_DIR / self.id
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.latest = None   # último resultado (para la API)
        store.save({"_id": self.id, "nombre": name, "tipo": "live", "estado": "en vivo",
                    "creado": now_iso(), "camara": url, "fuente": source})

    def start(self):
        SESSIONS[self.id] = self
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.stop_event.set()

    def _run(self):
        errors = 0
        while not self.stop_event.is_set() and time.time() - self.started < self.duration:
            t0 = time.time()
            try:
                frame = grab_frame(self.url)
                dets, per_zone, annotated = processor.analyze_frame(frame, self.zones)
                self.calls += 1
                errors = 0
                rec = {"t": round(time.time() - self.started, 1), "conteo": per_zone,
                       "totales": processor.totals_of(dets), "detecciones": len(dets)}
                self.window.append(rec)
                self.all_records.append(rec)
                cv2.imwrite(str(self.out_dir / "live.jpg"), annotated)
                counts, totals, plan = processor.aggregate(list(self.window), self.zones, self.phases, self.params)
                self.timeline.append({"t": rec["t"], "hora": time.strftime("%H:%M:%S"),
                                      "por_acceso": {a: sum(c.values()) - c.get("peaton", 0) for a, c in per_zone.items()},
                                      "peatones": rec["totales"].get("peaton", 0)})
                self.latest = {"promedio_por_acceso": counts, "promedio_total": totals, "plan": plan,
                               "ultimo_frame": rec, "imagen": f"results/{self.id}/live.jpg"}
                self.state = "live"
                store.update(self.id, {"frames_procesados": len(self.all_records)})
            except Exception as e:
                traceback.print_exc()
                errors += 1
                self.error = str(e)
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    self.state = "error"
                    break
            self.stop_event.wait(max(0, self.interval - (time.time() - t0)))
        self._finish()

    def _finish(self):
        if self.state != "error":
            self.state = "finished"
        summary = {"estado": "listo" if self.state == "finished" else "error", "terminado": now_iso(),
                   "llamadas_api": self.calls, "timeline": self.timeline, "error": self.error}
        if self.all_records:
            counts, totals, plan = processor.aggregate(self.all_records, self.zones, self.phases, self.params)
            summary.update({"promedio_por_acceso": counts, "promedio_total": totals, "plan": plan,
                            "fases": self.phases, "imagen": f"results/{self.id}/live.jpg"})
        store.update(self.id, summary)

    def status(self) -> dict:
        elapsed = time.time() - self.started
        return {"_id": self.id, "nombre": self.name, "fuente": self.source, "estado": self.state,
                "error": self.error, "llamadas_api": self.calls, "frames": len(self.all_records),
                "intervalo": self.interval, "transcurrido": round(elapsed),
                "restante": max(0, round(self.duration - elapsed)) if self.state in ("starting", "live") else 0,
                "timeline": self.timeline[-60:], **(self.latest or {})}


def start_session(form) -> LiveSession:
    params = webster.SignalParams.from_form(form)
    cam = get_camera(form.get("camera_id", ""))
    if cam:
        url, name, source = cam["url"], cam["name"], cam.get("source", "")
        zones = cam.get("zones") or zones_mod.DEFAULT_ZONES
        phases = cam.get("phases") or zones_mod.PHASES
    else:
        url = (form.get("camera_url") or "").strip()
        validate_url(url)
        name = form.get("nombre") or urlparse(url).hostname
        source = "Custom URL"
        zones, phases = zones_mod.load_layout()
    interval = float(form.get("interval") or 10)
    duration = min(float(form.get("duration") or 10), 60)    # máximo 60 min para cuidar la cuota
    s = LiveSession(name, url, zones, phases, params, interval, duration, source)
    s.start()
    return s

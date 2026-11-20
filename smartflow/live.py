"""Modo en vivo: transmite una cámara pública de tráfico (HLS, RTSP, MJPEG o JPEG) de forma fluida,
la analiza con Azure Computer Vision y actualiza el plan de semáforo en tiempo real.

Arquitectura (3 piezas por sesión):
  * FrameSource  - hilo que lee la cámara sin parar y guarda siempre el último frame.
  * LiveRenderer - dibuja cajas y zonas sobre cada frame y lo codifica a JPEG a LIVE_FPS
                   (stream MJPEG). Entre análisis de Azure las cajas siguen a los vehículos
                   con flujo óptico Lucas-Kanade (OpenCV), sin gastar llamadas a la API.
  * LiveSession  - hilo que cada N segundos envía el último frame a Azure, calcula el plan
                   de Webster y guarda cada medición en MongoDB.
"""
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

from . import config, detector, processor, webster, zones as zones_mod
from .storage import store, now_iso

CAMERAS_FILE = config.BASE_DIR / "cameras.json"
WINDOW = 12                 # el plan se calcula con los últimos 12 frames
MAX_CONSECUTIVE_ERRORS = 4
MAX_VIEWERS = 6             # cada espectador ocupa un hilo de Gunicorn
TRACK_WIDTH = 480           # resolución a la que se calcula el flujo óptico (rápido)
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


def is_snapshot(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".jpg", ".jpeg", ".png")) or "snapshot" in path


def fetch_snapshot(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "SmartFlow/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(15 * 1024 * 1024)
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("Could not read a frame from the camera.")
    return frame


def _resize_to(frame, width):
    h, w = frame.shape[:2]
    if w <= width:
        return frame
    return cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)


def _track_gray(frame):
    return cv2.cvtColor(_resize_to(frame, TRACK_WIDTH), cv2.COLOR_BGR2GRAY)


def _box_iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
class FrameSource(threading.Thread):
    """Lee la cámara de forma continua (reconecta si se corta) y publica cada frame."""

    def __init__(self, url, stop_event, on_frame):
        super().__init__(daemon=True)
        self.url, self.stop_event, self.on_frame = url, stop_event, on_frame
        self.cond = threading.Condition()
        self.frame, self.seq, self.error = None, 0, None

    def latest(self, newer_than: int, timeout: float):
        """Espera un frame más nuevo que `newer_than`. Devuelve (frame, seq) o (None, seq)."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq > newer_than or self.stop_event.is_set(), timeout)
            return (self.frame, self.seq) if self.seq > newer_than else (None, self.seq)

    def _publish(self, frame):
        with self.cond:
            self.frame, self.seq, self.error = frame, self.seq + 1, None
            self.cond.notify_all()
        self.on_frame(frame)

    def run(self):
        while not self.stop_event.is_set():
            try:
                if is_snapshot(self.url):
                    self._publish(fetch_snapshot(self.url))
                    self.stop_event.wait(1.0)            # una imagen JPEG no da más de ~1 fps
                else:
                    self._read_stream()
            except Exception as e:
                self.error = str(e)
                self.stop_event.wait(3)                  # reintenta la conexión

    def _read_stream(self):
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG,
                               [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 20000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 20000])
        if not cap.isOpened():
            raise RuntimeError("Could not open the camera stream.")
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if 1 <= fps <= 120 else 25
        t0, n = time.time(), 0
        try:
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise RuntimeError("Camera stream interrupted.")
                n += 1
                self._publish(frame)
                # HLS entrega segmentos de varios segundos de golpe: los reproducimos a velocidad
                # real para que el video se vea fluido en vez de "a saltos".
                ahead = t0 + n / fps - time.time()
                if ahead > 0:
                    self.stop_event.wait(min(ahead, 1.0))
                elif ahead < -2:
                    t0, n = time.time(), 0
        finally:
            cap.release()


# ---------------------------------------------------------------------------
class LiveRenderer:
    """Dibuja el video anotado a LIVE_FPS y mantiene las cajas pegadas a los vehículos."""

    def __init__(self, zone_polys):
        self.zone_polys = zone_polys
        self.lock = threading.Lock()
        self.cond = threading.Condition()
        self.jpeg, self.jpeg_seq = None, 0
        self.viewers = 0
        self.tracks = []          # [{clase, confianza, box:[x,y,w,h] normalizado, pts}]
        self.pending = None       # detecciones nuevas de Azure aún no incorporadas
        self.prev_gray = None
        self.next_render = 0.0
        self.render_times = deque(maxlen=30)
        self.history = deque(maxlen=int(config.LIVE_FPS * 6))   # (hora, gris) de los últimos ~6 s

    # --- llamado por el hilo de análisis ---
    def set_detections(self, dets, frame_shape, gray_at_analysis, captured_at, keep_azure=False):
        """keep_azure=True (refresco con YOLOX): conserva las cajas que solo vio Azure."""
        h, w = frame_shape[:2]
        boxes = [{"clase": d["clase"], "confianza": d["confianza"], "fuente": d.get("fuente", "azure"), "lost": 0,
                  "box": [d["x"] / w, d["y"] / h, d["w"] / w, d["h"] / h]} for d in dets]
        with self.lock:
            self.pending = (boxes, gray_at_analysis, captured_at, keep_azure)

    # --- llamado por FrameSource en cada frame ---
    def on_frame(self, frame):
        now = time.time()
        if self.viewers == 0 or now < self.next_render:
            return
        # acumulativo: con una cámara de 25-30 fps se logra LIVE_FPS en promedio
        self.next_render += 1.0 / config.LIVE_FPS
        if self.next_render < now:
            self.next_render = now
        try:
            view = _resize_to(frame, config.LIVE_STREAM_WIDTH)
            self._track(view)
            ok, buf = cv2.imencode(".jpg", self._draw(view), [cv2.IMWRITE_JPEG_QUALITY, config.LIVE_JPEG_QUALITY])
        except Exception:
            traceback.print_exc()
            return
        if ok:
            with self.cond:
                self.jpeg, self.jpeg_seq = buf.tobytes(), self.jpeg_seq + 1
                self.cond.notify_all()
            self.render_times.append(now)

    def fps(self) -> float:
        t = self.render_times
        if len(t) < 2 or time.time() - t[-1] > 2:
            return 0.0
        return round((len(t) - 1) / (t[-1] - t[0]), 1)

    # --- seguimiento con flujo óptico ---
    def _track(self, view):
        now = time.time()
        gray = _track_gray(view)
        gh, gw = gray.shape
        with self.lock:
            pending, self.pending = self.pending, None
        if pending:
            boxes, ref_gray, captured_at, keep_azure = pending
            if ref_gray.shape != gray.shape:
                ref_gray = cv2.resize(ref_gray, (gw, gh))
            for b in boxes:
                b["pts"] = self._features(ref_gray, b["box"], gw, gh)
            # Azure tarda ~1 s: ponemos las cajas al día recorriendo los frames intermedios
            prev = ref_gray
            for ts, g in list(self.history):
                if ts > captured_at and g.shape == prev.shape:
                    self._flow(boxes, prev, g, gw, gh)
                    prev = g
            if keep_azure:
                for t in self.tracks:
                    if t.get("fuente") in ("azure", "ambos") and not any(_box_iou(t["box"], b["box"]) > 0.3 for b in boxes):
                        boxes.append({**t, "fuente": "azure"})
            self.tracks, self.prev_gray = boxes, prev

        if self.prev_gray is not None and self.prev_gray.shape == gray.shape:
            self._flow(self.tracks, self.prev_gray, gray, gw, gh)
            # descarta cajas que salieron de la imagen o que perdieron su vehículo
            self.tracks = [t for t in self.tracks if t["lost"] < config.LIVE_FPS
                           and -0.1 < t["box"][0] + t["box"][2] / 2 < 1.1 and -0.1 < t["box"][1] + t["box"][3] / 2 < 1.1]
        self.prev_gray = gray
        self.history.append((now, gray))

    @staticmethod
    def _flow(tracks, prev, cur, gw, gh):
        """Mueve cada caja según la mediana del flujo óptico de sus puntos (con chequeo ida y vuelta)."""
        active = [t for t in tracks if t.get("pts") is not None and len(t["pts"])]
        for t in tracks:      # solo se borran las cajas que SÍ se seguían y perdieron el rastro
            if t.get("lost") and (t.get("pts") is None or not len(t["pts"])):
                t["lost"] += 1
        if not active:
            return
        pts = np.concatenate([t["pts"] for t in active])
        lk = dict(winSize=(21, 21), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03))
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, **lk)
        back, st2, _ = cv2.calcOpticalFlowPyrLK(cur, prev, nxt, None, **lk)
        fb = np.linalg.norm((pts - back).reshape(-1, 2), axis=1)
        ok = st.reshape(-1).astype(bool) & st2.reshape(-1).astype(bool) & (fb < 1.0)
        i = 0
        for t in active:
            n = len(t["pts"])
            good = ok[i:i + n]
            if good.sum() >= 2:
                d = np.median(nxt[i:i + n][good] - t["pts"][good], axis=0).reshape(-1)
                t["box"][0] += float(d[0]) / gw
                t["box"][1] += float(d[1]) / gh
                t["pts"] = nxt[i:i + n][good]
                t["lost"] = 0
            else:
                t["pts"] = None              # perdió el rastro
                t["lost"] += 1
            i += n

    @staticmethod
    def _features(gray, box, gw, gh):
        x, y, w, h = box
        x0, y0 = max(int((x + w * 0.15) * gw), 0), max(int((y + h * 0.15) * gh), 0)
        x1, y1 = min(int((x + w * 0.85) * gw), gw), min(int((y + h * 0.85) * gh), gh)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        p = cv2.goodFeaturesToTrack(gray[y0:y1, x0:x1], maxCorners=15, qualityLevel=0.01, minDistance=3)
        if p is None:
            return None
        return (p + np.array([x0, y0], np.float32)).astype(np.float32)

    def _draw(self, view):
        out = view.copy()
        h, w = out.shape[:2]
        for name, poly in self.zone_polys.items():
            pts = np.array([[int(px * w), int(py * h)] for px, py in poly], np.int32)
            cv2.polylines(out, [pts], True, (255, 255, 255), 1, cv2.LINE_AA)
        for t in self.tracks:
            bx, by, bw, bh = t["box"]
            x, y = int(bx * w), int(by * h)
            x2, y2 = int((bx + bw) * w), int((by + bh) * h)
            x, y, x2, y2 = max(x, 0), max(y, 0), min(x2, w - 1), min(y2, h - 1)
            if x2 <= x or y2 <= y:
                continue
            if t["clase"] == "peaton":   # privacidad: difumina la parte superior (rostro)
                top_h = max((y2 - y) // 3, 1)
                roi = out[y:y + top_h, x:x2]
                if roi.size:
                    out[y:y + top_h, x:x2] = cv2.GaussianBlur(roi, (21, 21), 0)
            color = config.CLASS_COLORS.get(t["clase"], (255, 255, 255))
            cv2.rectangle(out, (x, y), (x2, y2), color, 2, cv2.LINE_AA)
        return out

    # --- stream MJPEG para el navegador ---
    def mjpeg(self, is_active):
        with self.lock:
            self.viewers += 1
        try:
            last = -1
            while True:
                with self.cond:
                    self.cond.wait_for(lambda: self.jpeg_seq != last or not is_active(), timeout=5)
                    seq, jpg = self.jpeg_seq, self.jpeg
                if seq != last and jpg:
                    last = seq
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                elif not is_active():
                    break
        finally:
            with self.lock:
                self.viewers -= 1


# ---------------------------------------------------------------------------
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
        self.saved = 0
        self.last_analysis = 0.0
        self.started = time.time()
        self.stop_event = threading.Event()
        self.out_dir = config.RESULTS_DIR / self.id
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.latest = None   # último resultado (para la API)
        self.renderer = LiveRenderer(zones)
        self.frames = FrameSource(url, self.stop_event, self.renderer.on_frame)
        store.save({"_id": self.id, "nombre": name, "tipo": "live", "estado": "en vivo",
                    "creado": now_iso(), "camara": url, "fuente": source,
                    "fases": phases, "intervalo": self.interval, "modelos": processor.models_label()})

    def start(self):
        SESSIONS[self.id] = self
        self.frames.start()
        threading.Thread(target=self._run, daemon=True).start()
        if detector.available():
            threading.Thread(target=self._local_refresh, daemon=True).start()

    def stop(self):
        self.stop_event.set()

    def is_active(self) -> bool:
        return self.state in ("starting", "live") and not self.stop_event.is_set()

    def _run(self):
        errors, last_seq = 0, 0
        while not self.stop_event.is_set() and time.time() - self.started < self.duration:
            t0 = time.time()
            try:
                frame, last_seq = self.frames.latest(last_seq, timeout=25)
                if frame is None:
                    if self.stop_event.is_set():
                        break
                    raise RuntimeError(self.frames.error or "No frames received from the camera.")
                captured_at = time.time()
                small = processor.resize(frame)
                gray = _track_gray(small)
                dets, per_zone, annotated = processor.analyze_frame(small, self.zones)
                self.renderer.set_detections(dets, small.shape, gray, captured_at)
                self.calls += 1
                self.last_analysis = time.time()
                errors = 0
                self.error = None
                rec = {"t": round(time.time() - self.started, 1), "conteo": per_zone,
                       "totales": processor.totals_of(dets), "detecciones": len(dets),
                       "por_modelo": detector.source_counts(dets)}
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
                self.saved += store.add_measurement(processor.measurement(
                    self.id, "live", rec, dets, counts, totals, plan,
                    t=rec["t"], camara=self.name, fuente=self.source))
                store.update(self.id, {"frames_procesados": len(self.all_records), "llamadas_api": self.calls,
                                       "mediciones_guardadas": self.saved, "ultima_actualizacion": now_iso(),
                                       "promedio_por_acceso": counts, "promedio_total": totals, "plan": plan,
                                       "timeline": self.timeline, "imagen": self.latest["imagen"]})
            except Exception as e:
                traceback.print_exc()
                errors += 1
                self.error = str(e)
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    self.state = "error"
                    break
            self.stop_event.wait(max(0, self.interval - (time.time() - t0)))
        self._finish()

    def _local_refresh(self):
        """Refresca las cajas del video con YOLOX (~1 vez por segundo) mientras alguien mira.
        No reemplaza el análisis con Azure: los conteos y el plan salen del análisis completo."""
        last_seq = 0
        while not self.stop_event.is_set():
            t0 = time.time()
            if self.renderer.viewers and self.calls:     # empieza tras el primer análisis de Azure
                try:
                    frame, last_seq = self.frames.latest(last_seq, timeout=5)
                    if frame is not None:
                        captured_at = time.time()
                        small = processor.resize(frame)
                        dets = detector.detect(small)
                        self.renderer.set_detections(dets, small.shape, _track_gray(small), captured_at, keep_azure=True)
                except Exception:
                    traceback.print_exc()
            self.stop_event.wait(max(0.05, config.LIVE_LOCAL_REFRESH_SECONDS - (time.time() - t0)))

    def _finish(self):
        if self.state != "error":
            self.state = "finished"
        self.stop_event.set()                       # detiene también la lectura de la cámara
        with self.renderer.cond:
            self.renderer.cond.notify_all()         # cierra los streams abiertos
        summary = {"estado": "listo" if self.state == "finished" else "error", "terminado": now_iso(),
                   "llamadas_api": self.calls, "mediciones_guardadas": self.saved,
                   "timeline": self.timeline, "error": self.error}
        if self.all_records:
            counts, totals, plan = processor.aggregate(self.all_records, self.zones, self.phases, self.params)
            summary.update({"promedio_por_acceso": counts, "promedio_total": totals, "plan": plan,
                            "fases": self.phases, "imagen": f"results/{self.id}/live.jpg"})
        store.update(self.id, summary)

    def status(self) -> dict:
        elapsed = time.time() - self.started
        active = self.state in ("starting", "live")
        next_in = max(0, round(self.interval - (time.time() - self.last_analysis))) if self.last_analysis else None
        return {"_id": self.id, "nombre": self.name, "fuente": self.source, "estado": self.state,
                "error": self.error or (self.frames.error if active else None),
                "llamadas_api": self.calls, "frames": len(self.all_records),
                "intervalo": self.interval, "transcurrido": round(elapsed),
                "restante": max(0, round(self.duration - elapsed)) if active else 0,
                "fps": self.renderer.fps(), "stream": active, "proximo_analisis": next_in,
                "mediciones_guardadas": self.saved, "base_de_datos": store.name,
                "modelos": processor.models_label(),
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

"""Procesa una imagen o video: extrae frames, llama a Azure Computer Vision, cuenta por
acceso y calcula el plan de semáforo. Se ejecuta en un hilo en segundo plano."""
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from . import config, detector, vision, webster, zones as zones_mod
from .storage import store, now_iso

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CLASSES = ["auto", "moto", "bus", "camion", "bicicleta", "peaton"]


def resize(frame):
    h, w = frame.shape[:2]
    if w > config.MAX_IMAGE_WIDTH:
        scale = config.MAX_IMAGE_WIDTH / w
        frame = cv2.resize(frame, (config.MAX_IMAGE_WIDTH, int(h * scale)))
    return frame


def iter_frames(path: Path):
    """Devuelve (segundo, frame) cada FRAME_INTERVAL_SECONDS, hasta MAX_FRAMES."""
    if path.suffix.lower() in IMAGE_EXT:
        img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not read the image.")
        yield 0.0, resize(img)
        return
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Could not open the video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(int(fps * config.FRAME_INTERVAL_SECONDS), 1)
    count = 0
    for idx in range(0, max(total, 1), step):
        if count >= config.MAX_FRAMES:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            break
        count += 1
        yield idx / fps, resize(frame)
    cap.release()


def count_frames(path: Path) -> int:
    if path.suffix.lower() in IMAGE_EXT:
        return 1
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    step = max(int(fps * config.FRAME_INTERVAL_SECONDS), 1)
    return min(config.MAX_FRAMES, max(1, -(-total // step)))


def draw(frame, detections, zone_polys):
    out = frame.copy()
    h, w = out.shape[:2]
    overlay = out.copy()
    for name, poly in zone_polys.items():
        pts = np.array([[int(x * w), int(y * h)] for x, y in poly], np.int32)
        cv2.polylines(overlay, [pts], True, (255, 255, 255), 2, cv2.LINE_AA)
    out = cv2.addWeighted(overlay, 0.6, out, 0.4, 0)
    for d in detections:
        x, y, bw, bh = int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"])
        if d["clase"] == "peaton":   # privacidad: difumina la parte superior (rostro)
            top = out[y:y + max(bh // 3, 1), x:x + bw]
            if top.size:
                out[y:y + max(bh // 3, 1), x:x + bw] = cv2.GaussianBlur(top, (31, 31), 0)
        color = config.CLASS_COLORS.get(d["clase"], (255, 255, 255))
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2, cv2.LINE_AA)
    return out


def models_label() -> str:
    return "YOLOX + Azure Computer Vision" if detector.available() else "Azure Computer Vision"


def analyze_frame(frame, zone_polys):
    """Analiza un frame con Azure Computer Vision (siempre) y, si está disponible, con el
    detector local YOLOX; une ambos resultados. Cada detección indica su "fuente".
    Devuelve (detecciones, conteo_por_zona, imagen_anotada)."""
    h, w = frame.shape[:2]
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    dets = vision.analyze_image(buf.tobytes(), w, h)
    if detector.available():
        dets = detector.fuse(dets, detector.detect_tiled(frame))
    per_zone = {a: defaultdict(int) for a in zone_polys}
    for d in dets:
        d["zona"] = zones_mod.assign_zone(d, w, h, zone_polys)
        if d["zona"]:
            per_zone[d["zona"]][d["clase"]] += 1
    return dets, {a: dict(c) for a, c in per_zone.items()}, draw(frame, dets, zone_polys)


def aggregate(frame_records, zone_polys, phases, params):
    """frame_records: lista de {"conteo": {zona: {clase: n}}, "totales": {clase: n}}.
    Devuelve promedios por acceso, promedio total y el plan de semáforo."""
    n = max(len(frame_records), 1)
    approach_counts, approach_stats = {}, {}
    for a in zone_polys:
        avg = {c: sum(r["conteo"].get(a, {}).get(c, 0) for r in frame_records) / n for c in CLASSES}
        approach_counts[a] = {c: round(v, 2) for c, v in avg.items()}
        approach_stats[a] = {
            "pcu": sum(avg[c] * config.PCU[c] for c in config.PCU),
            "personas": sum(avg[c] * config.OCCUPANCY[c] for c in config.OCCUPANCY),
        }
    totals = {c: round(sum(r["totales"].get(c, 0) for r in frame_records) / n, 2) for c in CLASSES}
    plan = webster.compute_plan(approach_stats, phases, params, totals["peaton"])
    return approach_counts, totals, plan


def totals_of(dets):
    t = defaultdict(int)
    for d in dets:
        t[d["clase"]] += 1
    return dict(t)


def measurement(analysis_id, tipo, rec, dets, approach_counts, totals, plan, **extra) -> dict:
    """Documento que se guarda en MongoDB por cada frame analizado."""
    return {
        "analisis_id": analysis_id, "tipo": tipo, "fecha": datetime.now(timezone.utc),
        "conteo_por_acceso": rec["conteo"], "totales_frame": rec["totales"], "detecciones": len(dets),
        "objetos": [{k: d.get(k) for k in ("clase", "confianza", "zona", "fuente", "x", "y", "w", "h")} for d in dets],
        "detecciones_por_modelo": detector.source_counts(dets),
        "modelos": models_label(),
        "promedio_por_acceso": approach_counts, "promedio_total": totals,
        "plan": plan, **extra,
    }


def process(analysis_id: str, path: Path, params: webster.SignalParams):
    try:
        zone_polys, phases = zones_mod.load_layout()
        total_frames = count_frames(path)
        store.update(analysis_id, {"estado": "procesando", "total_frames": total_frames})
        out_dir = config.RESULTS_DIR / analysis_id
        out_dir.mkdir(parents=True, exist_ok=True)

        frames, saved_count = [], 0
        for i, (sec, frame) in enumerate(iter_frames(path)):
            dets, per_zone, annotated = analyze_frame(frame, zone_polys)
            img_name = f"frame_{i:03d}.jpg"
            cv2.imwrite(str(out_dir / img_name), annotated)
            rec = {"segundo": round(sec, 1), "imagen": f"results/{analysis_id}/{img_name}",
                   "conteo": per_zone, "totales": totals_of(dets), "detecciones": len(dets),
                   "por_modelo": detector.source_counts(dets)}
            frames.append(rec)
            counts, totals, plan = aggregate(frames, zone_polys, phases, params)
            saved_count += store.add_measurement(measurement(analysis_id, "video", rec, dets, counts, totals, plan,
                                                      frame=i, segundo=rec["segundo"]))
            store.update(analysis_id, {"frames_procesados": i + 1, "plan": plan,
                                       "promedio_por_acceso": counts, "promedio_total": totals,
                                       "mediciones_guardadas": saved_count})

        approach_counts, totals, plan = aggregate(frames, zone_polys, phases, params)
        store.update(analysis_id, {
            "estado": "listo", "terminado": now_iso(), "frames": frames,
            "promedio_por_acceso": approach_counts, "promedio_total": totals,
            "fases": phases, "plan": plan, "modelos": models_label(),
        })
    except Exception as e:
        traceback.print_exc()
        store.update(analysis_id, {"estado": "error", "error": str(e)})
    finally:
        try:
            path.unlink()      # privacidad: no guardamos el video original
        except OSError:
            pass

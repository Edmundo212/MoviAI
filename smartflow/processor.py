"""Procesa una imagen o video: extrae frames, llama a Azure Computer Vision, cuenta por
acceso y calcula el plan de semáforo. Se ejecuta en un hilo en segundo plano."""
import traceback
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from . import config, vision, webster, zones as zones_mod
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
        cv2.polylines(overlay, [pts], True, (255, 255, 255), 2)
        cx, cy = pts.mean(axis=0).astype(int)
        cv2.putText(overlay, name, (cx - 10 * len(name) // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)
    out = cv2.addWeighted(overlay, 0.6, out, 0.4, 0)
    for d in detections:
        x, y, bw, bh = int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"])
        if d["clase"] == "peaton":   # privacidad: difumina la parte superior (rostro)
            top = out[y:y + max(bh // 3, 1), x:x + bw]
            if top.size:
                out[y:y + max(bh // 3, 1), x:x + bw] = cv2.GaussianBlur(top, (31, 31), 0)
        color = config.CLASS_COLORS.get(d["clase"], (255, 255, 255))
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
        label = f'{d["clase"]} {d["confianza"]:.2f}'
        cv2.putText(out, label, (x, max(y - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(out, "Azure Computer Vision", (w - 260, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return out


def analyze_frame(frame, zone_polys):
    """Analiza un frame con Azure Computer Vision.
    Devuelve (detecciones, conteo_por_zona, imagen_anotada)."""
    h, w = frame.shape[:2]
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    dets = vision.analyze_image(buf.tobytes(), w, h)
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


def process(analysis_id: str, path: Path, params: webster.SignalParams):
    try:
        zone_polys, phases = zones_mod.load_layout()
        total_frames = count_frames(path)
        store.update(analysis_id, {"estado": "procesando", "total_frames": total_frames})
        out_dir = config.RESULTS_DIR / analysis_id
        out_dir.mkdir(parents=True, exist_ok=True)

        frames = []
        for i, (sec, frame) in enumerate(iter_frames(path)):
            dets, per_zone, annotated = analyze_frame(frame, zone_polys)
            img_name = f"frame_{i:03d}.jpg"
            cv2.imwrite(str(out_dir / img_name), annotated)
            frames.append({"segundo": round(sec, 1), "imagen": f"results/{analysis_id}/{img_name}",
                           "conteo": per_zone, "totales": totals_of(dets), "detecciones": len(dets)})
            store.update(analysis_id, {"frames_procesados": i + 1})

        approach_counts, totals, plan = aggregate(frames, zone_polys, phases, params)
        store.update(analysis_id, {
            "estado": "listo", "terminado": now_iso(), "frames": frames,
            "promedio_por_acceso": approach_counts, "promedio_total": totals,
            "fases": phases, "plan": plan,
        })
    except Exception as e:
        traceback.print_exc()
        store.update(analysis_id, {"estado": "error", "error": str(e)})
    finally:
        try:
            path.unlink()      # privacidad: no guardamos el video original
        except OSError:
            pass

"""Detector local YOLOX-S (ONNX, OpenCV DNN) que complementa a Azure Computer Vision.

Modelo: YOLOX-S entrenado en COCO, del model zoo oficial de OpenCV (licencia Apache-2.0):
https://huggingface.co/opencv/object_detection_yolox
Corre en CPU con OpenCV (sin PyTorch). Detecta mejor los vehículos pequeños o lejanos,
que el modelo general de Azure suele omitir.
"""
import threading

import cv2
import numpy as np

from . import config

# Clases COCO que nos interesan -> clase de SmartFlow
COCO_MAP = {0: ("person", "peaton"), 1: ("bicycle", "bicicleta"), 2: ("car", "auto"),
            3: ("motorcycle", "moto"), 5: ("bus", "bus"), 7: ("truck", "camion")}
INPUT = 640
STRIDES = (8, 16, 32)

_net = None
_lock = threading.Lock()
_grids = None


def available() -> bool:
    return config.LOCAL_DETECTOR_ENABLED and config.LOCAL_MODEL_PATH.exists()


def _load():
    global _net, _grids
    if _net is None:
        _net = cv2.dnn.readNet(str(config.LOCAL_MODEL_PATH))
        grids, strides = [], []
        for s in STRIDES:
            n = INPUT // s
            xv, yv = np.meshgrid(np.arange(n), np.arange(n))
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((n * n, 1), s))
        _grids = (np.concatenate(grids).astype(np.float32), np.concatenate(strides).astype(np.float32))
    return _net


def detect(frame, min_conf: float | None = None) -> list[dict]:
    """Devuelve detecciones {clase, etiqueta, confianza, x, y, w, h, fuente:"yolox"} en píxeles."""
    min_conf = config.LOCAL_MIN_CONFIDENCE if min_conf is None else min_conf
    h, w = frame.shape[:2]
    r = min(INPUT / h, INPUT / w)
    padded = np.full((INPUT, INPUT, 3), 114, np.uint8)
    padded[: int(h * r), : int(w * r)] = cv2.resize(frame, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR)
    blob = cv2.dnn.blobFromImage(padded.astype(np.float32))       # YOLOX: BGR, 0-255, sin normalizar

    with _lock:                     # OpenCV DNN no es thread-safe con la misma red
        net = _load()
        net.setInput(blob)
        out = net.forward()[0]      # (8400, 85)

    grid, stride = _grids
    xy = (out[:, :2] + grid) * stride
    wh = np.exp(out[:, 2:4]) * stride
    scores = out[:, 4:5] * out[:, 5:]
    cls = scores.argmax(1)
    conf = scores[np.arange(len(cls)), cls]
    keep = np.isin(cls, list(COCO_MAP)) & (conf >= min_conf)
    if not keep.any():
        return []
    xy, wh, cls, conf = xy[keep] / r, wh[keep] / r, cls[keep], conf[keep]
    boxes = np.concatenate([xy - wh / 2, wh], 1)

    dets = []
    # NMS por clase
    for c in np.unique(cls):
        idx = np.where(cls == c)[0]
        sel = cv2.dnn.NMSBoxes(boxes[idx].tolist(), conf[idx].tolist(), min_conf, 0.45)
        for i in np.array(sel).reshape(-1):
            x, y, bw, bh = boxes[idx[i]]
            x, y = max(float(x), 0.0), max(float(y), 0.0)
            bw, bh = min(float(bw), w - x), min(float(bh), h - y)
            label, clase = COCO_MAP[int(c)]
            dets.append({"clase": clase, "etiqueta": label, "confianza": round(float(conf[idx[i]]), 3),
                         "x": x, "y": y, "w": bw, "h": bh, "fuente": "yolox"})
    return dets


def detect_tiled(frame, min_conf: float | None = None) -> list[dict]:
    """Imagen completa + 2x2 recortes ampliados: los autos lejanos se ven más grandes.
    Une todo con NMS. Es local (gratis), así que no gasta cuota de Azure."""
    h, w = frame.shape[:2]
    dets = detect(frame, min_conf)
    if config.LOCAL_TILES:
        tw, th = int(w * 0.6), int(h * 0.6)            # recortes con 20 % de solape
        for ox in (0, w - tw):
            for oy in (0, h - th):
                for d in detect(frame[oy:oy + th, ox:ox + tw], min_conf):
                    # descarta cajas cortadas por el borde interior del recorte
                    if (ox and d["x"] < 2) or (oy and d["y"] < 2) or (ox == 0 and d["x"] + d["w"] > tw - 2)                             or (oy == 0 and d["y"] + d["h"] > th - 2):
                        continue
                    d["x"] += ox
                    d["y"] += oy
                    dets.append(d)
    return _nms(dets)


def _nms(dets, thr=0.45):
    out = []
    for d in sorted(dets, key=lambda d: -d["confianza"]):
        if all((d["clase"] == "peaton") != (o["clase"] == "peaton") or iou(d, o) < thr and not _contains(o, d)
               for o in out):
            out.append(d)
    return out


def _contains(big, small, tol=0.85) -> bool:
    """True si `small` está casi totalmente dentro de `big` (duplicado entre recortes)."""
    x1, y1 = max(big["x"], small["x"]), max(big["y"], small["y"])
    x2 = min(big["x"] + big["w"], small["x"] + small["w"])
    y2 = min(big["y"] + big["h"], small["y"] + small["h"])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter >= tol * small["w"] * small["h"]


def iou(a: dict, b: dict) -> float:
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2, y2 = min(a["x"] + a["w"], b["x"] + b["w"]), min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def fuse(azure_dets: list[dict], local_dets: list[dict], thr: float = 0.35) -> list[dict]:
    """Une detecciones de Azure y YOLOX. Si ambos ven el mismo objeto se cuenta una sola vez
    (fuente "ambos"); si solo uno lo ve, se conserva con su fuente."""
    fused = [{**d, "fuente": "azure"} for d in azure_dets]
    for ld in local_dets:
        best, best_iou = None, thr
        for fd in fused:
            if fd["fuente"] != "yolox" and (fd["clase"] == "peaton") == (ld["clase"] == "peaton"):
                v = iou(fd, ld)
                if v > best_iou:
                    best, best_iou = fd, v
        if best is not None:
            best["fuente"] = "ambos"
            best["confianza"] = max(best["confianza"], ld["confianza"])
        else:
            fused.append(ld)
    # el conductor de una moto/bicicleta o un pasajero no es un peatón
    vehicles = [d for d in fused if d["clase"] != "peaton"]
    return [d for d in fused if d["clase"] != "peaton" or not any(_center_in(d, v) for v in vehicles)]


def _center_in(d, v) -> bool:
    cx, cy = d["x"] + d["w"] / 2, d["y"] + d["h"] / 2
    return v["x"] <= cx <= v["x"] + v["w"] and v["y"] <= cy <= v["y"] + v["h"]


SOURCE_TAG = {"azure": "AZ", "yolox": "YX", "ambos": "AZ+YX"}


def source_counts(dets) -> dict:
    """Cuántas detecciones aportó cada modelo (para mostrarlo con transparencia)."""
    c = {"azure": 0, "yolox": 0, "ambos": 0}
    for d in dets:
        c[d.get("fuente", "azure")] += 1
    return c

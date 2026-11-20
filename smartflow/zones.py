"""Zonas de la intersección: asigna cada detección a un acceso (N, S, E, O).

Las zonas se definen como polígonos con coordenadas normalizadas (0 a 1) en zones.json.
Si no existe el archivo, se usa la división por diagonales (4 triángulos desde el centro).
"""
import json

from . import config

DEFAULT_ZONES = {
    "N": [[0, 0], [1, 0], [0.5, 0.5]],
    "E": [[1, 0], [1, 1], [0.5, 0.5]],
    "S": [[0, 1], [1, 1], [0.5, 0.5]],
    "O": [[0, 0], [0, 1], [0.5, 0.5]],
}

# Fases del semáforo: qué accesos reciben verde a la vez.
PHASES = {"Norte-Sur": ["N", "S"], "Este-Oeste": ["E", "O"]}


def load_layout() -> tuple[dict, dict]:
    """Devuelve (zonas, fases). zones.json: {"zones": {...}, "phases": {...}}"""
    if config.ZONES_FILE.exists():
        with open(config.ZONES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data["zones"], data.get("phases", PHASES)
    return DEFAULT_ZONES, PHASES


def _point_in_polygon(x: float, y: float, poly: list) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def assign_zone(det: dict, width: int, height: int, zones: dict) -> str | None:
    """Usa el punto inferior central de la caja (donde el vehículo toca la pista)."""
    px = (det["x"] + det["w"] / 2) / width
    py = min((det["y"] + det["h"]) / height, 0.999)
    for name, poly in zones.items():
        if _point_in_polygon(px, py, poly):
            return name
    return None

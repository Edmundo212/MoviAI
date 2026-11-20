"""Almacenamiento de análisis.

Si MONGODB_URI está definido en .env se usa MongoDB; si no, un archivo JSON local
(data/analyses.json). Ambas opciones tienen la misma interfaz.

Además de un documento por análisis (colección MONGODB_COLLECTION), cada frame analizado
se guarda como una "medición" en MONGODB_MEASUREMENTS_COLLECTION: conteos por acceso,
totales, flujos y plan de semáforo calculado en ese momento.
"""
import json
import logging
import threading
from datetime import datetime, timezone

from . import config

log = logging.getLogger("smartflow.storage")


class JsonStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        if not path.exists():
            path.write_text("{}", encoding="utf-8")

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, doc: dict):
        with self.lock:
            data = self._read()
            data[doc["_id"]] = doc
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def update(self, analysis_id: str, fields: dict):
        with self.lock:
            data = self._read()
            if analysis_id in data:
                data[analysis_id].update(fields)
                self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def get(self, analysis_id: str):
        return self._read().get(analysis_id)

    def list(self, limit=50):
        docs = sorted(self._read().values(), key=lambda d: d["creado"], reverse=True)
        return docs[:limit]

    def add_measurement(self, doc: dict):
        doc = {**doc, "fecha": doc["fecha"].isoformat(timespec="seconds")}
        with self.lock, open(config.DATA_DIR / "measurements.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        return True

    def ping(self):
        return True

    name = "json-local"


class MongoStore:
    def __init__(self, uri, db_name):
        from pymongo import MongoClient
        db = MongoClient(uri, serverSelectionTimeoutMS=8000)[db_name]
        self.col = db[config.MONGODB_COLLECTION]
        self.measurements = db[config.MONGODB_MEASUREMENTS_COLLECTION]
        try:
            self.measurements.create_index([("analisis_id", 1), ("fecha", 1)])
        except Exception as e:      # sin conexión al arrancar: se reintenta en cada escritura
            log.warning("MongoDB index not created: %s", e)

    def save(self, doc):
        self.col.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    def update(self, analysis_id, fields):
        self.col.update_one({"_id": analysis_id}, {"$set": fields})

    def get(self, analysis_id):
        return self.col.find_one({"_id": analysis_id})

    def list(self, limit=50):
        return list(self.col.find({}, {"frames": 0, "timeline": 0}).sort("creado", -1).limit(limit))

    def add_measurement(self, doc):
        """Guarda una medición; si MongoDB falla no detiene el análisis."""
        try:
            self.measurements.insert_one(dict(doc))
            return True
        except Exception as e:
            log.warning("MongoDB measurement not saved: %s", e)
            return False

    def ping(self):
        try:
            self.col.database.client.admin.command("ping")
            return True
        except Exception:
            return False

    name = "mongodb"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


store = (MongoStore(config.MONGODB_URI, config.MONGODB_DB) if config.MONGODB_URI
         else JsonStore(config.DATA_DIR / "analyses.json"))

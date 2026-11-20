"""Almacenamiento de análisis.

Si MONGODB_URI está definido en .env se usa MongoDB; si no, un archivo JSON local
(data/analyses.json). Ambas opciones tienen la misma interfaz.
"""
import json
import threading
from datetime import datetime, timezone

from . import config


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


class MongoStore:
    def __init__(self, uri, db_name):
        from pymongo import MongoClient
        self.col = MongoClient(uri, serverSelectionTimeoutMS=8000)[db_name]["analyses"]

    def save(self, doc):
        self.col.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    def update(self, analysis_id, fields):
        self.col.update_one({"_id": analysis_id}, {"$set": fields})

    def get(self, analysis_id):
        return self.col.find_one({"_id": analysis_id})

    def list(self, limit=50):
        return list(self.col.find({}, {"frames": 0}).sort("creado", -1).limit(limit))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


store = (MongoStore(config.MONGODB_URI, config.MONGODB_DB) if config.MONGODB_URI
         else JsonStore(config.DATA_DIR / "analyses.json"))

"""SmartFlow - semáforo adaptativo con Azure Computer Vision.

Local:      python app.py               -> http://localhost:5000
Servidor:   gunicorn -w 1 --threads 12 -b 127.0.0.1:8000 app:app
"""
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from smartflow import config, live, processor, webster
from smartflow.storage import store, now_iso

ALLOWED = processor.IMAGE_EXT | {".mp4", ".mov", ".avi", ".mkv", ".webm"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   # 200 MB


def render_index(error=None, live_error=None, code=200):
    historial = store.list(20)
    for h in historial:      # sesiones en vivo que se cortaron (p. ej. reinicio del servidor)
        if h.get("estado") == "en vivo" and h["_id"] not in live.SESSIONS:
            h["estado"] = "listo"
    return render_template("index.html", historial=historial, config=config,
                           cameras=live.load_cameras(), error=error, live_error=live_error), code


@app.get("/")
def index():
    return render_index()


# ---------- Análisis de video / imagen ----------
@app.post("/analizar")
def analizar():
    f = request.files.get("archivo")
    if not f or not f.filename:
        return render_index(error="Please select an image or video.", code=400)
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED:
        return render_index(error="This file type is not supported.", code=400)

    analysis_id = uuid.uuid4().hex[:12]
    path = config.UPLOAD_DIR / f"{analysis_id}{ext}"
    f.save(path)
    params = webster.SignalParams.from_form(request.form)
    store.save({
        "_id": analysis_id, "nombre": request.form.get("nombre") or secure_filename(f.filename),
        "archivo": secure_filename(f.filename), "tipo": "imagen" if ext in processor.IMAGE_EXT else "video",
        "estado": "en cola", "creado": now_iso(), "frames_procesados": 0, "total_frames": 0,
    })
    threading.Thread(target=processor.process, args=(analysis_id, path, params), daemon=True).start()
    return redirect(url_for("analisis", analysis_id=analysis_id))


@app.get("/analisis/<analysis_id>")
def analisis(analysis_id):
    doc = store.get(analysis_id)
    if not doc:
        abort(404)
    if doc.get("tipo") == "live":
        return redirect(url_for("live_page", session_id=analysis_id))
    return render_template("result.html", doc=doc)


@app.get("/api/analisis/<analysis_id>")
def api_analisis(analysis_id):
    doc = store.get(analysis_id)
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(doc)


# ---------- Cámara en vivo ----------
@app.post("/live/start")
def live_start():
    try:
        session = live.start_session(request.form)
    except Exception as e:
        return render_index(live_error=str(e), code=400)
    return redirect(url_for("live_page", session_id=session.id))


@app.get("/live/<session_id>")
def live_page(session_id):
    doc = store.get(session_id)
    if not doc:
        abort(404)
    return render_template("live.html", doc=doc)


@app.get("/api/live/<session_id>")
def api_live(session_id):
    s = live.SESSIONS.get(session_id)
    if s:
        return jsonify(s.status())
    doc = store.get(session_id)      # sesión terminada (o servidor reiniciado)
    if not doc:
        return jsonify({"error": "not found"}), 404
    doc["estado"] = "finished" if doc.get("estado") == "listo" else doc.get("estado")
    if doc["estado"] == "en vivo":
        doc["estado"] = "finished"
    return jsonify(doc)


@app.get("/live/<session_id>/stream.mjpg")
def live_stream(session_id):
    """Video en vivo anotado (MJPEG, ~LIVE_FPS fotogramas por segundo)."""
    s = live.SESSIONS.get(session_id)
    if not s or not s.is_active():
        abort(404)
    if s.renderer.viewers >= live.MAX_VIEWERS:
        return "Too many viewers", 429
    return Response(s.renderer.mjpeg(s.is_active), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"})


@app.get("/api/mediciones/<analysis_id>")
def api_mediciones(analysis_id):
    """Últimas mediciones guardadas en MongoDB para un análisis."""
    if not hasattr(store, "measurements"):
        return jsonify({"error": "MongoDB not configured", "base_de_datos": store.name}), 404
    limit = min(int(request.args.get("limit", 50)), 500)
    docs = list(store.measurements.find({"analisis_id": analysis_id}, {"objetos": 0})
                .sort("fecha", -1).limit(limit))
    for d in docs:
        d["_id"] = str(d["_id"])
    return jsonify(docs)


@app.post("/api/live/<session_id>/stop")
def api_live_stop(session_id):
    s = live.SESSIONS.get(session_id)
    if s:
        s.stop()
    return jsonify({"ok": True})


@app.get("/salud")
def salud():
    return jsonify({"ok": True, "computer_vision_configurado": bool(config.VISION_KEY),
                    "base_de_datos": store.name, "base_de_datos_conectada": store.ping(),
                    "sesiones_en_vivo": sum(1 for s in live.SESSIONS.values() if s.state in ("starting", "live"))})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

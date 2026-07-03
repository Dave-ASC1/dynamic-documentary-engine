"""
app.py
------
Dynamic Documentary Engine — Flask Backend

Minimal API wrapping the engine's public interface so a browser can
trigger film generation without anyone touching Python or a terminal.
This is the thin layer between the web/frontend UI and the real engine
pipeline (Sequencer.generate -> Assembler.render) — it contains no
sequencing logic of its own; that all lives in engine/ and is shared with
the CLI script via scripts/dde_runtime.py.

Endpoints:
    GET  /                   Serves the single-page frontend.
    POST /api/generate       Generates + renders a new film. Returns its
                              ordered sequence, the dissimilarity trace
                              behind each cut, and a playback URL.
    GET  /films/<filename>   Serves a rendered film file for playback.
    GET  /api/films          Lists previously generated films (saved as
                              analytical artifacts) for review.

Run:
    python3 web/backend/app.py
    then open http://127.0.0.1:5000 in a browser.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
FRONTEND_DIR = os.path.join(REPO_ROOT, "web", "frontend")

# The engine-driving logic (tracing, placeholder assets, render) lives in
# scripts/dde_runtime.py so this backend and the CLI validation script
# never drift apart on how a film is actually generated.
for _p in (REPO_ROOT, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dde_runtime  # noqa: E402
from flask import Flask, abort, jsonify, request, send_from_directory  # noqa: E402

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def frontend_assets(filename):
    """Serves style.css / app.js alongside index.html."""
    full_path = os.path.join(FRONTEND_DIR, filename)
    if not os.path.isfile(full_path):
        abort(404)
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.get_json(silent=True) or {}
    target = body.get("target_duration")
    if target is not None:
        try:
            target = int(target)
        except (TypeError, ValueError):
            return jsonify({"error": "target_duration must be an integer"}), 400

    try:
        result = dde_runtime.generate_and_render(target_duration=target)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result["film_url"] = f"/films/{result['film_filename']}"
    return jsonify(result)


@app.route("/films/<path:filename>")
def films(filename):
    return send_from_directory(dde_runtime.DEFAULT_FILMS, filename)


@app.route("/api/films")
def list_films():
    films_dir = dde_runtime.DEFAULT_FILMS
    if not os.path.isdir(films_dir):
        return jsonify([])

    items = []
    for fname in os.listdir(films_dir):
        if not fname.endswith(".mp4"):
            continue
        manifest_path = os.path.join(films_dir, os.path.splitext(fname)[0] + ".json")
        entry = {"film_url": f"/films/{fname}", "filename": fname}
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                manifest = json.load(f)
            entry["generated_at"] = manifest.get("generated_at")
            entry["target_duration"] = manifest.get("target_duration")
            entry["actual_duration"] = manifest.get("actual_duration")
            entry["slots"] = manifest.get("slots")
        items.append(entry)

    items.sort(key=lambda e: e.get("generated_at") or "", reverse=True)
    return jsonify(items)


if __name__ == "__main__":
    os.makedirs(dde_runtime.DEFAULT_FILMS, exist_ok=True)
    os.makedirs(dde_runtime.DEFAULT_ASSETS, exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)

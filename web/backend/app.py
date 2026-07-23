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

Media source:
    By default the backend generates from the real footage in
    local-media/assets/ (and writes films to local-media/films/) when that
    folder exists, so a browser demo uses real clips. If it does not exist
    (e.g. a fresh clone with no media yet), it falls back to the disposable
    placeholder workspace in demo/. Override either path explicitly with the
    DDE_ASSETS_PATH / DDE_FILMS_PATH environment variables.

Endpoints:
    GET  /                   Serves the single-page frontend.
    POST /api/generate       Generates + renders a new film. Returns its
                              ordered sequence, the dissimilarity trace
                              behind each cut, and a playback URL.
    GET  /films/<filename>   Serves a rendered film file for playback.
    GET  /api/films          Lists previously generated films (saved as
                              analytical artifacts) for review.
    DELETE /api/films/<filename>  Deletes a generated film and its manifest.

Run:
    python3 web/backend/app.py
    then open http://127.0.0.1:5000 in a browser.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.1.0
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


def _resolve_media_paths():
    """Pick the assets/films directories the demo should use.

    Priority: explicit env vars > real local media (if present) > the
    disposable placeholder workspace. Returned as absolute paths.
    """
    local_assets = os.path.join(REPO_ROOT, "local-media", "assets")
    local_films = os.path.join(REPO_ROOT, "local-media", "films")

    assets = os.environ.get("DDE_ASSETS_PATH")
    if not assets:
        assets = local_assets if os.path.isdir(local_assets) else dde_runtime.DEFAULT_ASSETS

    films = os.environ.get("DDE_FILMS_PATH")
    if not films:
        # Keep films next to whichever assets we chose.
        films = local_films if assets == local_assets else dde_runtime.DEFAULT_FILMS

    return os.path.abspath(assets), os.path.abspath(films)


ASSETS_PATH, FILMS_PATH = _resolve_media_paths()


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

    diversity_mode = bool(body.get("diversity_mode"))
    exact_duration = bool(body.get("exact_duration"))

    try:
        result = dde_runtime.generate_and_render(
            target_duration=target,
            assets_path=ASSETS_PATH,
            films_path=FILMS_PATH,
            diversity_mode=diversity_mode,
            exact_duration=exact_duration,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result["film_url"] = f"/films/{result['film_filename']}"
    return jsonify(result)


@app.route("/films/<path:filename>")
def films(filename):
    return send_from_directory(FILMS_PATH, filename)


@app.route("/api/films/<path:filename>", methods=["DELETE"])
def delete_film(filename):
    # Strip any path components the client sent so this can only ever touch
    # a file directly inside FILMS_PATH, never traverse elsewhere.
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".mp4"):
        return jsonify({"error": "Only generated .mp4 films can be deleted"}), 400

    film_path = os.path.join(FILMS_PATH, safe_name)
    if not os.path.isfile(film_path):
        return jsonify({"error": "Film not found"}), 404

    os.remove(film_path)

    manifest_path = os.path.splitext(film_path)[0] + ".json"
    if os.path.isfile(manifest_path):
        os.remove(manifest_path)

    return jsonify({"deleted": safe_name})


@app.route("/api/films")
def list_films():
    if not os.path.isdir(FILMS_PATH):
        return jsonify([])

    items = []
    for fname in os.listdir(FILMS_PATH):
        if not fname.endswith(".mp4"):
            continue
        manifest_path = os.path.join(FILMS_PATH, os.path.splitext(fname)[0] + ".json")
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
    os.makedirs(FILMS_PATH, exist_ok=True)
    os.makedirs(ASSETS_PATH, exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    print(f" * DDE media source : {ASSETS_PATH}")
    print(f" * DDE films output : {FILMS_PATH}")
    app.run(debug=True, port=port)

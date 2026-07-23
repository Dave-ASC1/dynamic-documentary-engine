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

Film topics ("collections"):
    Each film topic (World War II, Swiss, ...) is a self-contained folder
    under local-media/<Topic>/ — assets/ (source footage) and artifacts/
    (rendered films). dde_runtime.list_collections() auto-discovers every
    topic folder shaped that way; this backend never hardcodes a single
    media path, every request resolves paths through whichever collection
    the client selected.

Endpoints:
    GET  /                        Serves the single-page frontend.
    GET  /api/collections         Lists available film topics.
    POST /api/generate            Generates + renders a new film for a
                                   given collection. Returns its ordered
                                   sequence, the dissimilarity trace behind
                                   each cut, and a playback URL.
    GET  /films/<collection>/<filename>   Serves a rendered film file.
    GET  /api/films?collection=<id>       Lists previously generated films
                                           for that collection.
    DELETE /api/films/<collection>/<filename>  Deletes a generated film.

Run:
    python3 web/backend/app.py
    then open http://127.0.0.1:5000 in a browser.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.2.0
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


@app.route("/api/collections")
def collections():
    return jsonify(dde_runtime.list_collections())


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.get_json(silent=True) or {}

    collection_id = body.get("collection")
    if not collection_id:
        return jsonify({"error": "collection is required"}), 400

    collection = dde_runtime.get_collection(collection_id)
    if collection is None:
        return jsonify({
            "error": f"Unknown film topic '{collection_id}'.",
            "available": [c["id"] for c in dde_runtime.list_collections()],
        }), 404

    if collection["artifact_counts"].get("total", 0) == 0:
        return jsonify({
            "error": f"'{collection['name']}' has no footage yet. Add clips to "
                     f"local-media/{collection['folder']}/assets/a-roll, b-roll, "
                     f"or x-roll and try again."
        }), 400

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
            assets_path=collection["assets_path"],
            films_path=collection["films_path"],
            index_path=collection["index_path"],
            metadata_path=collection["metadata_path"],
            diversity_mode=diversity_mode,
            exact_duration=exact_duration,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result["collection_id"] = collection["id"]
    result["film_url"] = f"/films/{collection['id']}/{result['film_filename']}"
    return jsonify(result)


@app.route("/films/<collection_id>/<path:filename>")
def films(collection_id, filename):
    collection = dde_runtime.get_collection(collection_id)
    if collection is None:
        abort(404)
    return send_from_directory(collection["films_path"], filename)


@app.route("/api/films/<collection_id>/<path:filename>", methods=["DELETE"])
def delete_film(collection_id, filename):
    collection = dde_runtime.get_collection(collection_id)
    if collection is None:
        return jsonify({"error": f"Unknown film topic '{collection_id}'."}), 404

    # Strip any path components the client sent so this can only ever touch
    # a file directly inside this collection's films_path, never traverse
    # elsewhere.
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".mp4"):
        return jsonify({"error": "Only generated .mp4 films can be deleted"}), 400

    film_path = os.path.join(collection["films_path"], safe_name)
    if not os.path.isfile(film_path):
        return jsonify({"error": "Film not found"}), 404

    os.remove(film_path)

    manifest_path = os.path.splitext(film_path)[0] + ".json"
    if os.path.isfile(manifest_path):
        os.remove(manifest_path)

    return jsonify({"deleted": safe_name})


@app.route("/api/films")
def list_films():
    collection_id = request.args.get("collection")
    if not collection_id:
        return jsonify({"error": "collection query param is required"}), 400

    collection = dde_runtime.get_collection(collection_id)
    if collection is None:
        return jsonify({"error": f"Unknown film topic '{collection_id}'."}), 404

    films_path = collection["films_path"]
    if not os.path.isdir(films_path):
        return jsonify([])

    items = []
    for fname in os.listdir(films_path):
        if not fname.endswith(".mp4"):
            continue
        manifest_path = os.path.join(films_path, os.path.splitext(fname)[0] + ".json")
        entry = {
            "film_url": f"/films/{collection['id']}/{fname}",
            "filename": fname,
        }
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
    port = int(os.environ.get("PORT", 5000))
    for c in dde_runtime.list_collections():
        os.makedirs(c["films_path"], exist_ok=True)
        os.makedirs(c["assets_path"], exist_ok=True)
        print(f" * Collection '{c['id']}' ({c['name']}) — "
              f"{c['artifact_counts'].get('total', 0)} artifacts")
    app.run(host="0.0.0.0", debug=True, port=port)

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
import socket
import sys
import threading
import webbrowser

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
from engine.cancellation import CancellationToken, GenerationCancelled  # noqa: E402
from flask import Flask, abort, jsonify, request, send_from_directory  # noqa: E402

app = Flask(__name__, static_folder=None)


# ----------------------------------------------------------------------
# In-flight generation registry (for the Cancel button)
# ----------------------------------------------------------------------
#
# Rendering is a long, synchronous FFmpeg-bound job. To let the UI stop one
# partway through, the client makes up a job_id, sends it with the generate
# request, and can then POST it to /api/generate/cancel. The two requests
# land on different Flask threads, so the registry is mutex-guarded.
#
# Having the *client* supply the id keeps /api/generate a single
# request/response — no job-polling protocol — while still giving the
# cancel request something to name.

_active_jobs = {}
_active_jobs_lock = threading.Lock()


def _register_job(job_id):
    """Creates and registers a CancellationToken for job_id."""
    token = CancellationToken()
    with _active_jobs_lock:
        _active_jobs[job_id] = {
            "token": token,
            "progress": {"stage": "starting", "current": 0, "total": 1},
        }
    return token


def _release_job(job_id):
    """Drops job_id from the registry once its render has finished."""
    with _active_jobs_lock:
        _active_jobs.pop(job_id, None)


def _job_progress_recorder(job_id):
    """Returns a progress callback that stores the latest stage for job_id.

    The exhibit view polls this while a film renders. A feature-length film
    takes tens of minutes, so "still working" is not enough to tell a
    viewer — it needs to say which clip it's on.
    """
    def record(stage, current, total):
        with _active_jobs_lock:
            job = _active_jobs.get(job_id)
            if job is not None:
                job["progress"] = {
                    "stage": stage, "current": current, "total": total,
                }
    return record


@app.route("/api/generate/progress")
def generate_progress():
    """Reports how far along an in-flight generation is."""
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id query param is required"}), 400

    with _active_jobs_lock:
        job = _active_jobs.get(job_id)
        progress = dict(job["progress"]) if job else None

    if progress is None:
        # Finished, cancelled, or never started — all "not running" here.
        return jsonify({"running": False})
    return jsonify({"running": True, **progress})


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/exhibit")
def exhibit():
    """Gallery/kiosk view — see web/frontend/exhibit.html.

    Deliberately a separate page rather than a mode of the main one: the
    console is a researcher's instrument (topic and length pickers, the
    contrast trace, the film history), while this is a single button in
    front of the public.
    """
    return send_from_directory(FRONTEND_DIR, "exhibit.html")


@app.route("/<path:filename>")
def frontend_assets(filename):
    """Serves style.css / app.js alongside index.html."""
    full_path = os.path.join(FRONTEND_DIR, filename)
    if not os.path.isfile(full_path):
        abort(404)
    return send_from_directory(FRONTEND_DIR, filename)


def _synced_collection(collection):
    """Reconciles a topic's index against what's actually in its folders and
    returns it with fresh artifact counts.

    Media is added by dropping files into a topic's assets folders in
    Finder, so the index is only ever a cache of what's on disk. Syncing on
    request is what makes "drop a file in and it appears" true. It costs
    nothing in the steady state — only files not already indexed are
    probed, so a repeat sync with nothing new takes about a millisecond.

    A sync failure is swallowed: a topic that can't be reconciled should
    still be listed and usable with whatever was already indexed, rather
    than taking the whole page down.
    """
    try:
        dde_runtime.sync_media_library(
            collection["index_path"], collection["assets_path"]
        )
    except Exception:
        app.logger.exception("Could not sync collection %s", collection.get("id"))
        return collection
    return dde_runtime.get_collection(collection["id"]) or collection


@app.route("/api/collections")
def collections():
    # Synced here so the topic list and its clip counts reflect the folders
    # as they are right now, without needing a film to be generated first.
    return jsonify([_synced_collection(c) for c in dde_runtime.list_collections()])


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

    # Sync before the empty check, not after. Media detection used to happen
    # only inside generate_and_render, which the check below returns ahead
    # of — so a topic that started empty could never pick up its first
    # clips: refused for being empty, and never synced because it was
    # refused. Exactly the case that matters, since every new topic starts
    # empty and has footage added later.
    collection = _synced_collection(collection)

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

    # Client-supplied id so a later /api/generate/cancel can name this run.
    # Absent (e.g. an older client or a scripted call) means uncancellable,
    # which is the pre-existing behavior.
    job_id = body.get("job_id")
    token = _register_job(job_id) if job_id else None

    try:
        result = dde_runtime.generate_and_render(
            target_duration=target,
            assets_path=collection["assets_path"],
            films_path=collection["films_path"],
            index_path=collection["index_path"],
            metadata_path=collection["metadata_path"],
            titles_path=collection["titles_path"],
            diversity_mode=diversity_mode,
            exact_duration=exact_duration,
            cancel_token=token,
            progress_callback=_job_progress_recorder(job_id) if job_id else None,
        )
    except GenerationCancelled:
        # A deliberate stop, not a failure — 409 so the frontend can tell
        # "you cancelled this" apart from "the render broke".
        return jsonify({"cancelled": True, "job_id": job_id}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if job_id:
            _release_job(job_id)

    result["collection_id"] = collection["id"]
    result["film_url"] = f"/films/{collection['id']}/{result['film_filename']}"
    return jsonify(result)


@app.route("/api/generate/cancel", methods=["POST"])
def cancel_generate():
    """Stops an in-flight generation by job_id.

    Signals the token and kills whatever FFmpeg process that job currently
    has running, so the stop takes effect immediately rather than after the
    current clip finishes encoding. The generate request itself then
    unwinds and answers 409.
    """
    body = request.get_json(silent=True) or {}
    job_id = body.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id is required"}), 400

    with _active_jobs_lock:
        job = _active_jobs.get(job_id)
        token = job["token"] if job else None

    if token is None:
        # Already finished, already cancelled, or never existed — all the
        # same outcome from the caller's point of view: nothing is running.
        return jsonify({"cancelled": False, "reason": "not running"}), 404

    token.cancel()
    return jsonify({"cancelled": True, "job_id": job_id})


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


def _find_free_port(preferred):
    """Returns the first free port at or above `preferred`.

    The engine is started by double-clicking a launcher, by someone who
    has no way to diagnose "Address already in use" — most often caused by
    a copy of the engine still running in another window. Stepping to the
    next free port keeps that from being a dead end.

    5001 rather than 5000 to begin with: macOS runs AirPlay Receiver on
    5000, which silently takes the port on any modern Mac.
    """
    for candidate in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("0.0.0.0", candidate))
                return candidate
            except OSError:
                continue
    return preferred


if __name__ == "__main__":
    requested = int(os.environ.get("PORT", 5001))
    port = _find_free_port(requested)

    for c in dde_runtime.list_collections():
        os.makedirs(c["films_path"], exist_ok=True)
        os.makedirs(c["assets_path"], exist_ok=True)
        # Title folders are created up front so they're already visible in
        # Finder for footage to be dropped into, same as assets/.
        dde_runtime.ensure_titles_folders(c["titles_path"])
        print(f" * Collection '{c['id']}' ({c['name']}) — "
              f"{c['artifact_counts'].get('total', 0)} artifacts")

    url = f"http://127.0.0.1:{port}"
    print("\n" + "=" * 58)
    print("  The Dynamic Documentary Engine is running.")
    print(f"  Open this in your browser:  {url}")
    print("  To stop it, close this window.")
    print("=" * 58 + "\n")

    # Debug mode is off unless asked for. It restarts the server whenever a
    # file changes, which is useful while developing and confusing on a
    # machine that is only ever running the engine.
    debug = os.environ.get("DDE_DEBUG") == "1"

    # Open the browser for whoever launched it. Skipped in debug mode,
    # where the reloader would otherwise open a second window on restart.
    if not debug and os.environ.get("DDE_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host="0.0.0.0", debug=debug, port=port)

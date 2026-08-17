"""
dde_runtime.py
--------------
Dynamic Documentary Engine — Shared Runtime Helpers

Shared logic used by both the command-line validation script
(run_first_film.py) and the Flask backend (web/backend/app.py):
read-only selection tracing, disposable placeholder media generation, and
a single generate_and_render() entry point that drives the real public
API (Sequencer.generate -> Assembler.render) and returns a JSON-
serializable summary of what happened.

Keeping this in one place means the CLI script and the web backend can
never drift apart on how a film is actually generated — both call the
exact same code path against the real engine.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from engine import Sequencer, Assembler  # noqa: E402

METADATA_ROOT = os.path.join(REPO_ROOT, "metadata")
COLLECTIONS_METADATA_DIR = os.path.join(METADATA_ROOT, "collections")
COLLECTIONS_ROOT = os.path.join(REPO_ROOT, "local-media")

# Kept for backward compatibility with the CLI script's defaults — the
# "validation" collection specifically, not a stand-in for "whichever
# collection is selected" (that's what list_collections()/get_collection()
# below are for).
INDEX_PATH = os.path.join(COLLECTIONS_METADATA_DIR, "validation_collection_index.json")
METADATA_PATH = os.path.join(REPO_ROOT, "metadata", "validation")
DEFAULT_ASSETS = os.path.join(REPO_ROOT, "demo", "assets")
DEFAULT_FILMS = os.path.join(REPO_ROOT, "demo", "films")
DEFAULT_USAGE_STATS = "usage_stats.json"


# ----------------------------------------------------------------------
# Multi-collection ("film topic") registry
# ----------------------------------------------------------------------
#
# Per Dr. Campbell: each film topic (World War II, Swiss, ...) gets its
# own self-contained folder under local-media/ — assets/ (source footage)
# and artifacts/ (rendered films) — rather than one shared pool. A topic
# folder is discovered automatically the same way sync_media_library()
# auto-adopts new media files: anything under local-media/ shaped like
# <Name>/assets/ + <Name>/artifacts/ becomes a selectable collection, and
# gets an empty-but-valid metadata index the first time it's seen.

def _slugify_topic(name):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "collection"


def _create_empty_collection_index(index_path, topic_id, display_name):
    """Schema-valid, zero-artifact index for a freshly-discovered topic
    folder — mirrors what sync_media_library() will then populate once
    real files land in that topic's assets/ subfolders.
    """
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "collection_id": topic_id,
        "collection_name": display_name,
        "description": f"{display_name} film collection.",
        "version": "1.0.0",
        "created_at": now,
        "updated_at": now,
        "runtime_rules": {
            "min_duration_seconds": 35,
            "max_duration_seconds": 1800,
            "allow_repeat_artifacts": False,
            "save_generated_films": True,
        },
        "artifact_counts": {"total": 0, "a_roll": 0, "b_roll": 0, "x_roll": 0},
        "artifacts": [],
    }
    with open(index_path, "w") as f:
        json.dump(data, f, indent=2)


def list_collections():
    """Discovers every film-topic folder under local-media/.

    Returns a list of dicts, each: {id, name, folder, index_path,
    assets_path, films_path, metadata_path, artifact_counts}, sorted by
    display name.
    """
    if not os.path.isdir(COLLECTIONS_ROOT):
        return []

    results = []
    for entry in sorted(os.listdir(COLLECTIONS_ROOT)):
        folder = os.path.join(COLLECTIONS_ROOT, entry)
        if entry.startswith(".") or not os.path.isdir(folder):
            continue

        assets_path = os.path.join(folder, "assets")
        films_path = os.path.join(folder, "artifacts")
        if not (os.path.isdir(assets_path) and os.path.isdir(films_path)):
            continue  # doesn't have the expected topic-folder shape

        topic_id = _slugify_topic(entry)
        index_path = os.path.join(COLLECTIONS_METADATA_DIR, f"{topic_id}_collection_index.json")
        if not os.path.isfile(index_path):
            _create_empty_collection_index(index_path, topic_id, entry)

        with open(index_path) as f:
            data = json.load(f)

        results.append({
            "id": topic_id,
            "name": data.get("collection_name", entry),
            "folder": entry,
            "index_path": index_path,
            "assets_path": assets_path,
            "films_path": films_path,
            "titles_path": os.path.join(folder, TITLES_DIRNAME),
            "metadata_path": os.path.join(METADATA_ROOT, topic_id),
            "artifact_counts": data.get("artifact_counts", {"total": 0}),
        })

    results.sort(key=lambda c: c["name"].lower())
    return results


def get_collection(topic_id):
    """Returns the collection dict matching topic_id (see list_collections()
    for shape), or None if no such topic exists.
    """
    for c in list_collections():
        if c["id"] == topic_id:
            return c
    return None


# ----------------------------------------------------------------------
# Small formatting helpers
# ----------------------------------------------------------------------

def art_map(loader):
    """id -> enriched index summary dict."""
    return {a["artifact_id"]: a for a in loader.get_artifacts()}


def label(a):
    """Short human label for an artifact summary dict."""
    if a is None:
        return "(none)"
    return f"{a.get('title', a['artifact_id'])} [{a.get('artifact_type')}]"


def slot_label(slot):
    """Human label for a built slot dict (see generate_and_render()),
    regardless of whether it's a standalone artifact or a B-roll+X-roll
    pair — used to describe whichever artifact actually opened/closed a
    given run, since that's now chosen automatically per generation."""
    if slot["kind"] == "broll_xroll":
        return f"{slot['broll_title']} + {slot['xroll_title']} [B-roll+X-roll]"
    return f"{slot['title']} [{slot.get('artifact_type')}]"


def usage_stats_path(films_path):
    """Returns the per-output-folder artifact usage stats path."""
    return os.path.join(films_path, DEFAULT_USAGE_STATS)


def load_usage_counts(films_path):
    """Loads cross-run artifact usage counts for diversity mode."""
    path = usage_stats_path(films_path)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("artifact_usage", {})


def save_usage_counts(films_path, usage_counts):
    """Saves cross-run artifact usage counts for diversity mode."""
    os.makedirs(films_path, exist_ok=True)
    path = usage_stats_path(films_path)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_usage": usage_counts,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def merge_usage_counts(existing, generated):
    """Adds one generated film's usage counts into persisted usage counts."""
    merged = dict(existing)
    for artifact_id, count in generated.items():
        merged[artifact_id] = merged.get(artifact_id, 0) + count
    return merged


def dims(prev, cand):
    """Per-dimension contrast breakdown, mirroring the engine's scorer.

    Returns a list of short strings describing each dimension that adds
    to the dissimilarity score, so a human can see *why* the cut contrasts.
    """
    if prev is None:
        return ["first body pick — no previous clip to contrast against"]

    def g(d, k):
        return d.get(k) or d.get("content", {}).get(k)

    out = []
    if prev.get("artifact_type") != cand.get("artifact_type"):
        out.append(f"media type ({prev.get('artifact_type')}->{cand.get('artifact_type')})")
    if g(prev, "mood") and g(cand, "mood") and g(prev, "mood") != g(cand, "mood"):
        out.append(f"mood ({g(prev, 'mood')}->{g(cand, 'mood')})")
    if g(prev, "pacing") and g(cand, "pacing") and g(prev, "pacing") != g(cand, "pacing"):
        out.append(f"pacing ({g(prev, 'pacing')}->{g(cand, 'pacing')})")

    pt = set(prev.get("tags") or prev.get("content", {}).get("tags", []))
    ct = set(cand.get("tags") or cand.get("content", {}).get("tags", []))
    new_tags = ct - pt
    if new_tags:
        out.append(f"+{len(new_tags)} new tags")

    pth = set(prev.get("theme") or prev.get("content", {}).get("theme", []))
    cth = set(cand.get("theme") or cand.get("content", {}).get("theme", []))
    new_th = cth - pth
    if new_th:
        out.append(f"+{len(new_th)} new themes")

    pg = prev.get("geography") or prev.get("file", {}).get("geography")
    cg = cand.get("geography") or cand.get("file", {}).get("geography")
    if pg and cg and pg != cg:
        out.append(f"geography ({pg}->{cg})")

    pl = g(prev, "dominant_lines")
    cl = g(cand, "dominant_lines")
    if pl and cl and pl != cl:
        out.append(f"lines ({pl}->{cl})")

    return out or ["(identical on every scored dimension)"]


# ----------------------------------------------------------------------
# Read-only instrumentation of the selector
# ----------------------------------------------------------------------

class SelectionTracer:
    """Wraps a live ArtifactSelector to record each decision, without
    changing any selection behavior."""

    def __init__(self, selector):
        self.selector = selector
        self.events = []
        self._state = {}

        self._orig_select = selector.select_next
        self._orig_juxta = selector._apply_juxtaposition_filter
        self._orig_weighted = selector._weighted_random_select

        selector.select_next = self._select_next
        selector._apply_juxtaposition_filter = self._juxta
        selector._weighted_random_select = self._weighted

    def _select_next(self, candidates, current_mood=None, target_pacing=None):
        self._state["kind"] = "primary"
        return self._orig_select(
            candidates, current_mood=current_mood, target_pacing=target_pacing
        )

    def _juxta(self, candidates):
        prev = self.selector._last_selected
        ranking = [
            (a, self.selector._compute_dissimilarity_score(prev, a))
            for a in candidates
        ]
        ranking.sort(key=lambda t: t[1], reverse=True)
        self._state["prev"] = prev
        self._state["ranking"] = ranking
        return self._orig_juxta(candidates)

    def _weighted(self, candidates):
        chosen = self._orig_weighted(candidates)
        self.events.append({
            "kind": self._state.get("kind", "primary"),
            "prev": self._state.get("prev"),
            "ranking": self._state.get("ranking"),
            "pool": list(candidates),
            "chosen": chosen,
        })
        self._state["prev"] = None
        self._state["ranking"] = None
        return chosen


def instrument_pairing(selector, tracer):
    """Wraps select_pairing (B-roll -> X-roll) so pairing decisions show up
    in the same tracer as primary picks. Kept separate from SelectionTracer
    since select_pairing is a distinct method, not a variant of select_next.
    """
    orig_pairing = selector.select_pairing

    def _pairing(candidates):
        tracer._state["kind"] = "pairing"
        return orig_pairing(candidates)

    selector.select_pairing = _pairing


# ----------------------------------------------------------------------
# Placeholder media generation
# ----------------------------------------------------------------------

_FFMPEG_COLORS = {
    "orange": "orange", "gray": "gray", "blue": "blue", "green": "green",
    "red": "red", "yellow": "yellow", "white": "white", "black": "black",
    "brown": "0x8B4513", "purple": "0x800080", "silver": "0xC0C0C0",
    "amber": "0xFFBF00",
}
_FALLBACK_PALETTE = ["red", "green", "blue", "orange", "purple",
                     "teal", "0x8B4513", "gray", "0xFF1493", "0x00CED1"]


def _find_font():
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf",
              "/System/Library/Fonts/Supplemental/Times New Roman.ttf"):
        if os.path.exists(p):
            return p
    return None


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def _make_video(path, color, dur, freq, has_audio, label_text, font):
    dur = max(1, int(round(dur)))
    safe = "".join(c for c in label_text if c.isalnum() or c == " ").strip()[:28]
    inputs = ["-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=25:d={dur}"]
    if has_audio:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={freq}:d={dur}"]
    vf = []
    if font and safe:
        vf = ["-vf", (f"drawtext=fontfile={font}:text='{safe}':fontcolor=white:"
                      f"fontsize=18:x=(w-text_w)/2:y=(h-text_h)/2:"
                      f"box=1:boxcolor=black@0.5:boxborderw=6")]
    tail = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if has_audio:
        tail += ["-c:a", "aac", "-shortest"]
    cmd = ["ffmpeg", "-y"] + inputs + vf + tail + [path]
    if _run(cmd):
        return True
    # Retry without the text overlay if drawtext is unavailable.
    cmd = ["ffmpeg", "-y"] + inputs + tail + [path]
    return _run(cmd)


def _make_audio(path, dur, freq):
    dur = max(1, int(round(dur)))
    return _run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"sine=frequency={freq}:d={dur}", path])


def ensure_assets(loader, assets_path):
    """Create a disposable placeholder file for every artifact that lacks one."""
    os.makedirs(assets_path, exist_ok=True)
    font = _find_font()
    made, existed = 0, 0
    for i, a in enumerate(loader.get_artifacts()):
        fname = a.get("filename")
        if not fname:
            continue
        out = os.path.join(assets_path, fname)
        if os.path.exists(out):
            existed += 1
            continue
        dur = a.get("duration_seconds", 8)
        freq = 220 + (i * 55) % 880
        colors = a.get("dominant_colors") or []
        color = _FFMPEG_COLORS.get(colors[0], _FALLBACK_PALETTE[i % len(_FALLBACK_PALETTE)]) \
            if colors else _FALLBACK_PALETTE[i % len(_FALLBACK_PALETTE)]
        atype = a.get("artifact_type")
        title = a.get("title", a["artifact_id"])
        if atype == "X-roll":
            ok = _make_audio(out, dur, freq)
        elif atype == "B-roll":
            ok = _make_video(out, color, dur, freq, has_audio=False, label_text=title, font=font)
        else:  # A-roll
            ok = _make_video(out, color, dur, freq, has_audio=True, label_text=title, font=font)
        made += 1
        if not ok:
            raise RuntimeError(f"Failed to generate placeholder asset for {a['artifact_id']}")
    return {"created": made, "existing": existed}


# ----------------------------------------------------------------------
# Media library auto-sync — real collection only (not the demo/ bootstrap)
# ----------------------------------------------------------------------
#
# The engine only ever selects from artifacts listed in the collection
# index; it never scans local-media/assets/ on its own. This reconciles
# the two: any real file dropped into a-roll/ b-roll/ x-roll/ that isn't
# indexed yet gets an entry with auto-inferred metadata (duration via
# ffprobe, dominant color via ffmpeg frame sampling, a pacing heuristic
# from clip length). Any indexed entry whose backing file has been
# deleted is dropped from the index rather than silently replaced by a
# placeholder — deleting a file is enough to retire it, symmetric with
# adding one, and this is what keeps a missing file from ever being
# regenerated as a green-screen stand-in again.

_ROLL_SUBDIRS = {"A-roll": "a-roll", "B-roll": "b-roll", "X-roll": "x-roll"}

_MEDIA_EXTENSIONS = {
    "A-roll": (".mov", ".mp4", ".m4v"),
    "B-roll": (".mov", ".mp4", ".m4v"),
    "X-roll": (".wav", ".mp3", ".m4a", ".aac"),
}

# Coarse named-color palette for auto-tagging video dominant color —
# not exhaustive, just enough to give auto-discovered clips *some*
# scoreable contrast signal without hand-authored tags.
_COLOR_PALETTE = {
    "red": (200, 40, 40), "orange": (220, 120, 40), "yellow": (210, 200, 60),
    "green": (60, 150, 70), "cyan": (60, 170, 190), "blue": (50, 90, 190),
    "purple": (120, 70, 170), "pink": (210, 110, 160), "brown": (110, 80, 50),
    "gray": (130, 130, 130), "black": (25, 25, 25), "white": (230, 230, 230),
}


def _probe_duration(path):
    """Media duration in seconds via ffprobe, or None if it can't be read."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        return round(float(proc.stdout.strip()), 3)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def _nearest_color_name(rgb):
    r, g, b = rgb
    best, best_dist = "gray", float("inf")
    for name, (cr, cg, cb) in _COLOR_PALETTE.items():
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best, best_dist = name, dist
    return best


def _probe_dominant_color(path):
    """Best-effort average frame color: ffmpeg scales the frame to a
    single pixel (the resize filter averages as it downsamples), then we
    map that RGB triple to the nearest named color."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "1", "-i", path,
             "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"],
            capture_output=True, timeout=15,
        )
        px = proc.stdout[:3]
        if len(px) != 3:
            return None
        return _nearest_color_name(tuple(px))
    except (subprocess.SubprocessError, OSError):
        return None


def _infer_pacing(duration):
    """Coarse pacing heuristic from clip length — best-effort only; it
    has no idea what's actually happening in the shot."""
    if duration is None:
        return None
    if duration <= 6:
        return "fast"
    if duration <= 15:
        return "medium"
    return "slow"


def _humanize_title(filename):
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = stem.replace("_", " ").replace("-", " ")
    return " ".join(w if not w.islower() else w.capitalize() for w in stem.split())


def _mint_artifact_id(prefix, filename, taken):
    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_") or "clip"
    candidate = f"auto_{prefix}_{stem}"
    n = 2
    while candidate in taken:
        candidate = f"auto_{prefix}_{stem}_{n}"
        n += 1
    return candidate


def sync_media_library(index_path, assets_path):
    """Reconciles the collection index against what's actually on disk.

    Returns {"added": [artifact_id, ...], "removed": [artifact_id, ...]}.
    Rewrites index_path only if something actually changed.
    """
    with open(index_path) as f:
        data = json.load(f)

    artifacts = data.get("artifacts", [])
    existing_ids = {a["artifact_id"] for a in artifacts}

    kept = []
    removed = []
    for a in artifacts:
        fname = a.get("filename")
        full = os.path.join(assets_path, fname) if fname else None
        if full and os.path.isfile(full):
            kept.append(a)
        else:
            removed.append(a["artifact_id"])

    indexed_filenames = {a["filename"] for a in kept if a.get("filename")}
    id_prefix = {"A-roll": "a", "B-roll": "b", "X-roll": "x"}
    added = []

    for artifact_type, subdir in _ROLL_SUBDIRS.items():
        dirpath = os.path.join(assets_path, subdir)
        if not os.path.isdir(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if fname.startswith("."):
                continue
            if not fname.lower().endswith(_MEDIA_EXTENSIONS[artifact_type]):
                continue
            rel = f"{subdir}/{fname}"
            if rel in indexed_filenames:
                continue

            full = os.path.join(dirpath, fname)
            duration = _probe_duration(full)
            entry = {
                "artifact_id": _mint_artifact_id(id_prefix[artifact_type], fname, existing_ids),
                "artifact_type": artifact_type,
                "role": "body",
                "filename": rel,
                "duration_seconds": duration if duration is not None else 8.0,
                "title": _humanize_title(fname),
                "weight": 0.5,
                "can_repeat": False,
                "must_not_follow": [],
            }
            pacing = _infer_pacing(duration)
            if pacing:
                entry["pacing"] = pacing
            if artifact_type in ("A-roll", "B-roll"):
                color = _probe_dominant_color(full)
                if color:
                    entry["tags"] = [f"color-{color}"]

            existing_ids.add(entry["artifact_id"])
            kept.append(entry)
            added.append(entry["artifact_id"])

    if added or removed:
        counts = Counter(a["artifact_type"] for a in kept)
        data["artifacts"] = kept
        data["artifact_counts"] = {
            "total": len(kept),
            "a_roll": counts.get("A-roll", 0),
            "b_roll": counts.get("B-roll", 0),
            "x_roll": counts.get("X-roll", 0),
        }
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    return {"added": added, "removed": removed}


def _trim_film_to_duration(film_path, target_duration, video_codec="libx264",
                            audio_codec="aac", pix_fmt="yuv420p"):
    """Re-encodes film_path in place, cutting it to exactly target_duration
    seconds if it currently runs longer. Re-encoding rather than stream
    copy is what lets the cut land on an exact second instead of snapping
    to the nearest keyframe. Returns True if a trim was actually applied.
    """
    current = _probe_duration(film_path)
    if current is None or current <= target_duration:
        return False

    tmp_path = film_path + ".trim.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", film_path, "-t", str(target_duration),
        "-c:v", video_codec, "-c:a", audio_codec, "-pix_fmt", pix_fmt,
        "-movflags", "+faststart", tmp_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        return False

    if proc.returncode != 0 or not os.path.isfile(tmp_path):
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        return False

    os.replace(tmp_path, film_path)
    return True


# ----------------------------------------------------------------------
# Fixed opening/closing title cards
# ----------------------------------------------------------------------
#
# Per Dr. Campbell: the randomized B-roll+X-roll bookends the sequencer
# already generates stay as-is (that's the "every screening is different"
# mechanic) — this is a separate, always-identical title card and end
# card wrapped around the *entire* rendered film, the same way a real
# screening opens on a title slate and closes on credits regardless of
# what played in between.

_SERIF_FONT = "/System/Library/Fonts/Supplemental/Georgia.ttf"
_SANS_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
_CARD_WHITE = (255, 255, 255)
_CARD_MUTED = (170, 176, 190)

# Each line is (text, font_path, size, rgb_color); an empty text acts as a
# vertical spacer sized to its own font size. Rendered via Pillow rather
# than ffmpeg's drawtext filter, since drawtext requires libfreetype and
# isn't reliably compiled into every ffmpeg build (it wasn't in this one).
OPENING_CARD_LINES = [
    ("WELCOME TO THE", _SANS_FONT, 30, _CARD_MUTED),
    ("Dynamic Documentary Engine", _SERIF_FONT, 60, _CARD_WHITE),
    ("", None, 34, _CARD_WHITE),
    ("Faculty Supervisor: Dr. Betsy Campbell", _SANS_FONT, 26, _CARD_WHITE),
    ("Created by: Oluwafemisola David Ademoye", _SANS_FONT, 26, _CARD_WHITE),
    ("Collaborator: Omotola Ajibike Ajao", _SANS_FONT, 26, _CARD_WHITE),
]

CLOSING_CARD_LINES = [
    ("THE END", _SERIF_FONT, 72, _CARD_WHITE),
    ("", None, 34, _CARD_WHITE),
    ("Thanks for watching", _SANS_FONT, 30, _CARD_MUTED),
]

OPENING_CARD_SECONDS = 6
CLOSING_CARD_SECONDS = 4

# Per-collection title pieces
# ---------------------------
# Per Dr. Campbell (2026-08-17): the opening and closing pieces must not be
# hard-coded — each film topic needs its own, since a World War II opener
# (she floated a ~2-minute narrated description) has nothing to do with a
# Swiss one. So each topic folder gets:
#
#   local-media/<Topic>/titles/opening/   <- drop a video file here
#   local-media/<Topic>/titles/closing/
#
# Drop a finished video in either folder and it becomes that topic's
# opening/closing piece, at whatever length it happens to be. Leave a
# folder empty and the film falls back to the generated text card above.
# This deliberately mirrors how assets/ already works — Betsy adds media in
# Finder, never touching code or a terminal.
TITLES_DIRNAME = "titles"
OPENING_DIRNAME = "opening"
CLOSING_DIRNAME = "closing"

# Video containers accepted as a title piece. Audio-only files are not
# eligible — a title piece has to put something on screen.
TITLE_MEDIA_EXTENSIONS = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm")


def ensure_titles_folders(titles_path):
    """Creates the opening/ and closing/ subfolders for a topic, each with
    a short README explaining what to drop in. Called on startup so the
    folders are already sitting there in Finder for Betsy to fill.
    """
    if not titles_path:
        return
    for sub, when in ((OPENING_DIRNAME, "start"), (CLOSING_DIRNAME, "end")):
        folder = os.path.join(titles_path, sub)
        os.makedirs(folder, exist_ok=True)
        readme = os.path.join(folder, "README.txt")
        if not os.path.isfile(readme):
            try:
                with open(readme, "w") as f:
                    f.write(
                        f"Put ONE video file here to play at the {when} of every\n"
                        f"film generated for this topic.\n\n"
                        f"Accepted formats: {', '.join(TITLE_MEDIA_EXTENSIONS)}\n"
                        f"Any length is fine — a few seconds or a few minutes.\n\n"
                        f"Leave this folder empty and the standard generated\n"
                        f"text card is used instead.\n\n"
                        f"If more than one video is here, the first by filename\n"
                        f"is used, so name them 01_..., 02_... to be sure which.\n"
                    )
            except OSError:
                pass


def find_title_piece(titles_path, which):
    """Returns the path to a topic's custom opening/closing video, or None
    to fall back to the generated text card.

    Args:
        titles_path (str): The topic's titles/ folder.
        which (str):       OPENING_DIRNAME or CLOSING_DIRNAME.

    Returns:
        str or None: Path to the video file, or None if the folder is empty
                     (or holds only the README / non-video files).
    """
    if not titles_path:
        return None
    folder = os.path.join(titles_path, which)
    if not os.path.isdir(folder):
        return None

    candidates = sorted(
        f for f in os.listdir(folder)
        if not f.startswith(".")
        and f.lower().endswith(TITLE_MEDIA_EXTENSIONS)
    )
    if not candidates:
        return None
    return os.path.join(folder, candidates[0])


def _render_card_image(path, lines, width, height, bg_color=(0, 0, 0)):
    """Renders a centered block of multi-line text onto a solid background
    PNG. `lines` is [(text, font_path, size, rgb_color), ...]; a blank
    text acts as a spacer sized to its own font size.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    resolved = []
    for text, font_path, size, color in lines:
        font = None
        if font_path and os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, size)
            except OSError:
                font = None
        if font is None:
            font = ImageFont.load_default(size)
        line_h = (draw.textbbox((0, 0), text, font=font)[3] if text else size)
        resolved.append((text, font, color, line_h))

    line_gap = 16
    total_h = sum(h for _, _, _, h in resolved) + line_gap * (len(resolved) - 1)
    y = (height - total_h) / 2

    for text, font, color, line_h in resolved:
        if text:
            bbox = draw.textbbox((0, 0), text, font=font)
            x = (width - (bbox[2] - bbox[0])) / 2 - bbox[0]
            draw.text((x, y - bbox[1]), text, font=font, fill=color)
        y += line_h + line_gap

    img.save(path)


def _make_text_card(path, lines, duration, width, height, fps, bg_color=(0, 0, 0)):
    """Renders a static, silent title/credits card: a Pillow-drawn PNG
    looped into a short video clip. Silent audio track (rather than no
    audio at all) so it concatenates cleanly with the main film's audio
    stream via the concat demuxer.
    """
    duration = max(1, int(round(duration)))
    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = os.path.join(tmpdir, "card.png")
        try:
            _render_card_image(png_path, lines, width, height, bg_color)
        except Exception:
            return False

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-r", str(fps), "-i", png_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-t", str(duration),
            path,
        ]
        return _run(cmd)


def _has_audio_stream(path):
    """True if the file carries at least one audio stream."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return bool(proc.stdout.strip())


def _prepare_title_piece(src, dest, width, height, fps):
    """Normalizes a user-supplied title video into a segment the concat
    filter will accept alongside the rendered film.

    A file Betsy drops in titles/opening/ can be any resolution, aspect,
    frame rate, or codec, and may have no audio track at all — concat
    requires every input to match on all of those and to carry both a video
    and an audio stream. So the piece is letterboxed to the film's frame
    (rather than stretched, which would distort it), re-timed to the film's
    fps, and given a silent audio track if it has none.

    Returns True on success.
    """
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )

    cmd = ["ffmpeg", "-y", "-i", src]
    if _has_audio_stream(src):
        maps = ["-map", "0:v:0", "-map", "0:a:0"]
    else:
        # Silent stereo bed so the piece still has an audio stream to
        # concat against; -shortest stops it at the video's length.
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        maps = ["-map", "0:v:0", "-map", "1:a:0", "-shortest"]

    cmd += ["-vf", video_filter, "-r", str(fps)] + maps + [
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2",
        dest,
    ]
    return _run(cmd)


def title_card_durations(titles_path=None):
    """Returns (opening_seconds, closing_seconds) for whatever will actually
    wrap the film — a custom piece's real length if the topic has one, else
    the fixed generated-card length.

    Needed before rendering, because "exact duration" trims the dynamic
    sequence by however much the cards will add, and that has to be the
    real number rather than the default when a topic supplies its own
    (potentially minutes-long) piece.
    """
    opening = OPENING_CARD_SECONDS
    closing = CLOSING_CARD_SECONDS

    custom_open = find_title_piece(titles_path, OPENING_DIRNAME)
    if custom_open:
        probed = _probe_duration(custom_open)
        if probed:
            opening = probed

    custom_close = find_title_piece(titles_path, CLOSING_DIRNAME)
    if custom_close:
        probed = _probe_duration(custom_close)
        if probed:
            closing = probed

    return opening, closing


def _wrap_with_title_cards(film_path, output_width, output_height, output_fps,
                            video_codec="libx264", audio_codec="aac", pix_fmt="yuv420p",
                            titles_path=None):
    """Prepends an opening title piece and appends a closing one around
    film_path, re-encoding the three parts together into a single file at
    the same path. Returns True on success; leaves film_path untouched if
    either piece fails to render.

    If the collection supplies its own video in titles/opening/ or
    titles/closing/, that is used; otherwise the generated text card is.
    The two are interchangeable here — both are normalized to the same
    frame size, fps and stream layout before the join.

    Uses the concat *filter* (decoded-frame level), not the concat
    *demuxer* (container-level splicing) — the demuxer approach, even
    when re-encoding, can leave a small audio/video timestamp
    discontinuity at each splice point that plays back as a sliver of the
    previous segment's audio bleeding into the next. The filter graph
    guarantees continuous, monotonic timestamps across the join instead.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        open_path = os.path.join(tmpdir, "open_card.mp4")
        close_path = os.path.join(tmpdir, "close_card.mp4")

        custom_open = find_title_piece(titles_path, OPENING_DIRNAME)
        if custom_open:
            ok = _prepare_title_piece(
                custom_open, open_path, output_width, output_height, output_fps
            )
        else:
            ok = _make_text_card(open_path, OPENING_CARD_LINES, OPENING_CARD_SECONDS,
                                  output_width, output_height, output_fps)

        custom_close = find_title_piece(titles_path, CLOSING_DIRNAME)
        if custom_close:
            ok = ok and _prepare_title_piece(
                custom_close, close_path, output_width, output_height, output_fps
            )
        else:
            ok = ok and _make_text_card(close_path, CLOSING_CARD_LINES, CLOSING_CARD_SECONDS,
                                         output_width, output_height, output_fps)
        if not ok:
            return False

        tmp_out = film_path + ".withcards.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", open_path,
            "-i", os.path.abspath(film_path),
            "-i", close_path,
            "-filter_complex",
            "[0:v:0][0:a:0][1:v:0][1:a:0][2:v:0][2:a:0]concat=n=3:v=1:a=1[outv][outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", video_codec, "-c:a", audio_codec, "-pix_fmt", pix_fmt,
            "-r", str(output_fps),
            "-movflags", "+faststart", tmp_out,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except (subprocess.SubprocessError, OSError):
            if os.path.isfile(tmp_out):
                os.remove(tmp_out)
            return False

        if proc.returncode != 0 or not os.path.isfile(tmp_out):
            if os.path.isfile(tmp_out):
                os.remove(tmp_out)
            return False

        os.replace(tmp_out, film_path)
        return True


# ----------------------------------------------------------------------
# High-level entry point
# ----------------------------------------------------------------------

def generate_and_render(
    target_duration=None,
    assets_path=DEFAULT_ASSETS,
    films_path=DEFAULT_FILMS,
    index_path=INDEX_PATH,
    metadata_path=METADATA_PATH,
    diversity_mode=False,
    juxtaposition_pool_size=None,
    exact_duration=False,
    title_cards=True,
    titles_path=None,
    cancel_token=None,
):
    """Runs the real engine end to end and returns a JSON-serializable summary.

    Drives Sequencer.generate() -> Assembler.render() exactly as the CLI
    script does, records the dissimilarity trace behind each cut, ensures
    placeholder media exists for any artifact missing a real file, renders
    the film, and writes a manifest JSON next to it so the run remains
    reviewable later (generated films are saved as analytical artifacts,
    not just playback output).

    exact_duration (bool): By default the film is assembled from whole,
        untrimmed clips and lands at or under target_duration — real
        footage is never cut, but a lumpy combination of clip lengths can
        undershoot by a few seconds. Set True to instead let the sequence
        run past target_duration using whole clips, then trim the final
        rendered file down to exactly target_duration — this guarantees
        the exact length but does cut off whatever was playing at that
        instant, mid-shot or mid-sound. Only takes effect if a
        target_duration is given and the collection has enough footage to
        reach it in the first place.

    title_cards (bool): Wraps the rendered film with an opening title
        piece and a closing one — per Dr. Campbell's request, every
        screening opens and closes on the same slate regardless of what the
        randomized sequence in between looks like. Defaults on for real
        screenings; the CLI/tests can turn it off to skip the extra
        render time.

    titles_path (str): The collection's titles/ folder. A video dropped in
        titles/opening/ or titles/closing/ becomes that topic's own piece,
        at whatever length it is; an empty folder falls back to the
        generated text card. This is what lets each genre carry its own
        opening/closing rather than sharing one hard-coded slate.

    cancel_token: Optional CancellationToken. When supplied, the run stops
        between pipeline stages and kills the in-flight FFmpeg process if
        cancelled, raising GenerationCancelled instead of returning.

    Returns:
        dict: JSON-serializable summary — collection info, the ordered
              slots, the selection trace, and the rendered film's path.
    """
    # The demo/ path is a disposable bootstrap workspace whose index entries
    # are *meant* to have no real file yet — ensure_assets() below fills
    # them in with placeholders. Real media libraries (local-media/assets/
    # or any other real path) get the opposite treatment: sync new real
    # files in, and drop any index entry whose file has gone missing,
    # rather than ever placeholder-generating a stand-in for it.
    is_demo_mode = os.path.abspath(assets_path) == os.path.abspath(DEFAULT_ASSETS)
    library_sync = None
    if not is_demo_mode and os.path.isdir(assets_path):
        library_sync = sync_media_library(index_path, assets_path)

    usage_counts = load_usage_counts(films_path) if diversity_mode else {}
    sequencer = Sequencer(
        index_path,
        diversity_mode=diversity_mode,
        usage_counts=usage_counts,
        juxtaposition_pool_size=juxtaposition_pool_size,
    )
    loader = sequencer.loader
    amap = art_map(loader)

    tracer = SelectionTracer(sequencer.selector)
    instrument_pairing(sequencer.selector, tracer)

    sequence = sequencer.generate(
        target_duration=target_duration, allow_overshoot=exact_duration
    )

    slots = []
    for entry in sequence:
        if isinstance(entry, tuple):
            b, x = entry
            bd, xd = amap.get(b, {}), amap.get(x, {})
            slots.append({
                "kind": "broll_xroll",
                "broll_id": b,
                "xroll_id": x,
                "broll_title": bd.get("title", b),
                "xroll_title": xd.get("title", x),
                "role": bd.get("role", "body"),
                "duration_seconds": bd.get("duration_seconds", 0),
            })
        else:
            d = amap.get(entry, {})
            slots.append({
                "kind": "standalone",
                "artifact_id": entry,
                "title": d.get("title", entry),
                "artifact_type": d.get("artifact_type"),
                "role": d.get("role", "body"),
                "duration_seconds": d.get("duration_seconds", 0),
            })

    trace = []
    for ev in tracer.events:
        chosen = ev["chosen"]
        if chosen is None:
            continue
        ranking = ev["ranking"] or []
        trace.append({
            "kind": ev["kind"],
            "previous": label(ev["prev"]),
            "candidates": [
                {"title": label(a), "score": s, "chosen": a is chosen}
                for a, s in ranking[:6]
            ],
            "chosen": label(chosen),
            "contrast": dims(ev["prev"], chosen),
        })

    if is_demo_mode:
        ensure_assets(loader, assets_path)
    assembler = Assembler(
        loader=loader,
        assets_path=assets_path,
        films_path=films_path,
        metadata_path=metadata_path,
        cancel_token=cancel_token,
    )
    film_path = assembler.render(sequence)

    # Title pieces sit outside the dynamic sequence, but "exact duration"
    # should still mean the whole file matches target_duration — so the
    # trim target is the requested length minus however long the pieces
    # will add, not the full requested length. Measured from the actual
    # pieces, since a topic's own opener can run minutes rather than the
    # generated card's fixed few seconds.
    opening_seconds, closing_seconds = (
        title_card_durations(titles_path) if title_cards else (0, 0)
    )
    title_card_seconds = opening_seconds + closing_seconds

    # A topic's title pieces can be longer than the whole film that was
    # asked for, which leaves no room to trim into. Report that rather
    # than silently overshooting the requested length.
    titles_exceed_target = (
        target_duration is not None
        and title_cards
        and title_card_seconds >= target_duration
    )

    trimmed = False
    if exact_duration and target_duration is not None:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        dynamic_target = target_duration - title_card_seconds
        if dynamic_target > 0:
            trimmed = _trim_film_to_duration(
                film_path, dynamic_target,
                video_codec=assembler.video_codec,
                audio_codec=assembler.audio_codec,
                pix_fmt=assembler.pix_fmt,
            )

    cards_added = False
    if title_cards:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        cards_added = _wrap_with_title_cards(
            film_path,
            output_width=assembler.output_width,
            output_height=assembler.output_height,
            output_fps=assembler.output_fps,
            video_codec=assembler.video_codec,
            audio_codec=assembler.audio_codec,
            pix_fmt=assembler.pix_fmt,
            titles_path=titles_path,
        )

    usage_stats = None
    if diversity_mode:
        usage_counts = merge_usage_counts(usage_counts, sequencer.generated_usage)
        usage_stats = save_usage_counts(films_path, usage_counts)

    # Always read the real duration back off the final file — it reflects
    # whatever combination of trimming and title cards actually happened,
    # rather than trying to reconstruct it from slot durations (which only
    # ever describe the pre-trim, pre-cards dynamic sequence).
    actual_duration = _probe_duration(film_path)
    if actual_duration is None:
        actual_duration = sum(s["duration_seconds"] for s in slots) + title_card_seconds

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection_id": loader.collection.get("collection_id"),
        "collection_name": loader.collection.get("collection_name"),
        "target_duration": target_duration,
        "actual_duration": actual_duration,
        # Opening/closing are generated per run — read the label off the
        # actual chosen slots, not fixed collection metadata.
        "opening": slot_label(slots[0]) if slots else "(none)",
        "closing": slot_label(slots[-1]) if slots else "(none)",
        "slots": slots,
        "trace": trace,
        "film_path": film_path,
        "film_filename": os.path.basename(film_path),
        "diversity_mode": diversity_mode,
        "usage_stats_path": usage_stats,
        "library_sync": library_sync,
        "exact_duration": exact_duration,
        "trimmed": trimmed,
        "title_cards": cards_added,
        # Which opening/closing actually wrapped this film — a filename
        # when the topic supplies its own piece, None for the generated
        # text card. Lets the UI show what played without re-scanning.
        "opening_title_piece": (
            os.path.basename(find_title_piece(titles_path, OPENING_DIRNAME))
            if title_cards and find_title_piece(titles_path, OPENING_DIRNAME) else None
        ),
        "closing_title_piece": (
            os.path.basename(find_title_piece(titles_path, CLOSING_DIRNAME))
            if title_cards and find_title_piece(titles_path, CLOSING_DIRNAME) else None
        ),
        "title_card_seconds": title_card_seconds if title_cards else 0,
        "titles_exceed_target": titles_exceed_target,
    }

    manifest_path = os.path.splitext(film_path)[0] + ".json"
    with open(manifest_path, "w") as f:
        json.dump(result, f, indent=2)
    result["manifest_path"] = manifest_path

    return result

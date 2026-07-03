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
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from engine import Sequencer, Assembler  # noqa: E402

INDEX_PATH = os.path.join(
    REPO_ROOT, "metadata", "validation", "validation_collection_index.json"
)
METADATA_PATH = os.path.join(REPO_ROOT, "metadata", "validation")
DEFAULT_ASSETS = os.path.join(REPO_ROOT, "demo", "assets")
DEFAULT_FILMS = os.path.join(REPO_ROOT, "demo", "films")


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
# High-level entry point
# ----------------------------------------------------------------------

def generate_and_render(
    target_duration=None,
    assets_path=DEFAULT_ASSETS,
    films_path=DEFAULT_FILMS,
    index_path=INDEX_PATH,
    metadata_path=METADATA_PATH,
):
    """Runs the real engine end to end and returns a JSON-serializable summary.

    Drives Sequencer.generate() -> Assembler.render() exactly as the CLI
    script does, records the dissimilarity trace behind each cut, ensures
    placeholder media exists for any artifact missing a real file, renders
    the film, and writes a manifest JSON next to it so the run remains
    reviewable later (generated films are saved as analytical artifacts,
    not just playback output).

    Returns:
        dict: JSON-serializable summary — collection info, the ordered
              slots, the selection trace, and the rendered film's path.
    """
    sequencer = Sequencer(index_path)
    loader = sequencer.loader
    amap = art_map(loader)

    tracer = SelectionTracer(sequencer.selector)
    instrument_pairing(sequencer.selector, tracer)

    sequence = sequencer.generate(target_duration=target_duration)

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

    ensure_assets(loader, assets_path)
    assembler = Assembler(
        loader=loader,
        assets_path=assets_path,
        films_path=films_path,
        metadata_path=metadata_path,
    )
    film_path = assembler.render(sequence)

    # Summing slot durations gives the true screen time, matching the
    # actual rendered film length for both standalone A-roll and paired
    # B-roll/X-roll slots.
    actual_duration = sum(s["duration_seconds"] for s in slots)

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
    }

    manifest_path = os.path.splitext(film_path)[0] + ".json"
    with open(manifest_path, "w") as f:
        json.dump(result, f, indent=2)
    result["manifest_path"] = manifest_path

    return result

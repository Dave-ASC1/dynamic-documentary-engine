"""
run_first_film.py
-----------------
Dynamic Documentary Engine — End-to-End Validation Run

Drives the REAL public API end to end:

    Sequencer.generate()  ->  ordered, juxtaposition-driven sequence
    Assembler.render()    ->  a playable film file

and prints a readable trace explaining, at each cut, why the chosen clip
was among the most DISSIMILAR available (the engine's core aesthetic).

To make the render work before real footage exists, this script first
generates disposable placeholder media (flat-color video + tone audio,
optionally labelled with the clip title) for every artifact, into a
gitignored demo folder. Drop your real files into the same folder later
(matching each artifact's filename) and the exact same run produces a real
documentary — nothing in the engine changes.

The instrumentation here is READ-ONLY: it wraps the selector's internal
scoring methods to observe the ranked candidate pool at each decision. It
never alters what the engine chooses.

Usage:
    python3 scripts/run_first_film.py                 # full run + render
    python3 scripts/run_first_film.py --target 120    # aim for ~120s
    python3 scripts/run_first_film.py --no-render      # trace only, skip FFmpeg
    python3 scripts/run_first_film.py --seed 7         # reproducible sequence

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import argparse
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

from engine import Sequencer, Assembler  # noqa: E402

INDEX_PATH = os.path.join(
    REPO_ROOT, "metadata", "validation", "validation_collection_index.json"
)
METADATA_PATH = os.path.join(REPO_ROOT, "metadata", "validation")
DEFAULT_ASSETS = os.path.join(REPO_ROOT, "demo", "assets")
DEFAULT_FILMS = os.path.join(REPO_ROOT, "demo", "films")

BAR = "=" * 72
DIM = "-" * 72


# ----------------------------------------------------------------------
# Small formatting helpers
# ----------------------------------------------------------------------

def _art_map(loader):
    """id -> enriched index summary dict."""
    return {a["artifact_id"]: a for a in loader.get_artifacts()}


def _label(a):
    """Short human label for an artifact summary dict."""
    if a is None:
        return "(none)"
    return f"{a.get('title', a['artifact_id'])} [{a.get('artifact_type')}]"


def _dims(prev, cand):
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
        types = {a.get("artifact_type") for a in candidates}
        # A pool that is entirely X-roll is the sequencer asking for a B-roll's
        # audio partner; anything else is a normal body pick.
        self._state["kind"] = "pairing" if types == {"X-roll"} else "primary"
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


# ----------------------------------------------------------------------
# Trace printing
# ----------------------------------------------------------------------

def print_trace(events):
    print(f"\n{BAR}\nSELECTION TRACE — why each pick maximises contrast\n{BAR}")
    step = 0
    for ev in events:
        kind = ev["kind"]
        prev = ev["prev"]
        chosen = ev["chosen"]
        if chosen is None:
            continue
        step += 1
        tag = "B-roll audio pairing" if kind == "pairing" else "body pick"
        print(f"\nStep {step}  [{tag}]")
        print(f"  previous : {_label(prev)}")

        ranking = ev["ranking"]
        if ranking:
            score_of = {id(a): s for a, s in ranking}
            print("  candidates by dissimilarity (higher = more unlike previous):")
            for a, s in ranking[:6]:
                mark = " <== CHOSEN" if a is chosen else ""
                print(f"      {s:>2}  {_label(a)}{mark}")
            if len(ranking) > 6:
                print(f"      ... (+{len(ranking) - 6} more)")
            pool_ids = ", ".join(p.get("artifact_id") for p in ev["pool"])
            print(f"  juxtaposition pool (top candidates): {pool_ids}")
            chosen_score = score_of.get(id(chosen))
            print(f"  --> chose {_label(chosen)}  (dissimilarity {chosen_score})")
            print(f"      contrast: {', '.join(_dims(prev, chosen))}")
        else:
            print(f"  --> chose {_label(chosen)}")
            print(f"      {_dims(prev, chosen)[0]}")


def print_sequence(sequence, amap):
    print(f"\n{BAR}\nASSEMBLED FILM ORDER  ({len(sequence)} slots)\n{BAR}")
    total = 0.0
    for i, entry in enumerate(sequence):
        if isinstance(entry, tuple):
            b, x = entry
            bd = amap.get(b, {})
            xd = amap.get(x, {})
            dur = bd.get("duration_seconds", 0)
            total += dur
            print(f"  {i + 1:>2}. [B+X {dur:>4.0f}s]  {bd.get('title', b)}"
                  f"  +audio: {xd.get('title', x)}")
        else:
            d = amap.get(entry, {})
            dur = d.get("duration_seconds", 0)
            total += dur
            role = d.get("role", "body")
            anchor = "  <-- opening" if role == "opening" else (
                "  <-- closing" if role == "closing" else "")
            print(f"  {i + 1:>2}. [{d.get('artifact_type', '?'):<6} {dur:>4.0f}s]"
                  f"  {d.get('title', entry)}{anchor}")
    print(f"\n  approx. total runtime: {total:.0f}s")


def print_uniqueness(sequencer, amap, target, runs):
    print(f"\n{BAR}\nUNIQUENESS CHECK — {runs} independent generations\n{BAR}")
    seen = []
    for r in range(runs):
        seq = sequencer.generate(target_duration=target)
        seen.append(tuple(str(e) for e in seq))
        titles = []
        for e in seq:
            if isinstance(e, tuple):
                titles.append(amap.get(e[0], {}).get("title", e[0]).split()[0] + "+aud")
            else:
                titles.append(amap.get(e, {}).get("title", e).split()[0])
        print(f"  run {r + 1}: {' -> '.join(titles)}")
    distinct = len(set(seen))
    print(f"\n  {distinct}/{runs} generations were distinct orderings.")


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


def _make_video(path, color, dur, freq, has_audio, label, font):
    dur = max(1, int(round(dur)))
    safe = "".join(c for c in label if c.isalnum() or c == " ").strip()[:28]
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
            ok = _make_video(out, color, dur, freq, has_audio=False, label=title, font=font)
        else:  # A-roll
            ok = _make_video(out, color, dur, freq, has_audio=True, label=title, font=font)
        made += 1
        if not ok:
            print(f"  ! failed to generate placeholder for {a['artifact_id']}")
    print(f"  placeholder assets: {made} created, {existed} already present "
          f"(font overlay: {'yes' if font else 'no'})")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="DDE end-to-end validation run.")
    ap.add_argument("--target", type=int, default=90,
                    help="Target film duration in seconds (default: 90).")
    ap.add_argument("--seed", type=int, default=None,
                    help="Seed RNG for a reproducible sequence.")
    ap.add_argument("--runs", type=int, default=3,
                    help="How many extra generations for the uniqueness check.")
    ap.add_argument("--no-render", action="store_true",
                    help="Skip the FFmpeg render (trace only).")
    ap.add_argument("--assets-path", default=DEFAULT_ASSETS)
    ap.add_argument("--films-path", default=DEFAULT_FILMS)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"{BAR}\nDYNAMIC DOCUMENTARY ENGINE — end-to-end validation run\n{BAR}")

    sequencer = Sequencer(INDEX_PATH)
    loader = sequencer.loader
    amap = _art_map(loader)
    coll = loader.collection

    counts = coll.get("artifact_counts", {})
    print(f"collection : {coll.get('collection_name')}  (id: {coll.get('collection_id')})")
    print(f"artifacts  : {counts.get('total')} total — "
          f"{counts.get('a_roll')} A-roll, {counts.get('b_roll')} B-roll, "
          f"{counts.get('x_roll')} X-roll")
    print(f"opening    : {_label(amap.get(loader.get_opening_artifact_id()))}")
    print(f"closing    : {_label(amap.get(loader.get_closing_artifact_id()))}")
    print(f"target     : {args.target}s"
          + (f"   (seed {args.seed})" if args.seed is not None else "   (unseeded)"))

    # Instrument, then generate through the real API.
    tracer = SelectionTracer(sequencer.selector)
    sequence = sequencer.generate(target_duration=args.target)

    print_trace(tracer.events)
    print_sequence(sequence, amap)

    # Uniqueness check reuses the same sequencer (fresh state each generate()).
    if args.runs > 0:
        print_uniqueness(sequencer, amap, args.target, args.runs)

    # Render the film we traced above.
    if args.no_render:
        print(f"\n{BAR}\nRENDER SKIPPED (--no-render)\n{BAR}")
        return 0

    print(f"\n{BAR}\nRENDER — placeholder media -> film\n{BAR}")
    ensure_assets(loader, args.assets_path)
    assembler = Assembler(
        loader=loader,
        assets_path=args.assets_path,
        films_path=args.films_path,
        metadata_path=METADATA_PATH,
    )
    try:
        film_path = assembler.render(sequence)
    except Exception as e:
        print(f"\nRender failed: {e}")
        return 1

    print(f"\nFilm rendered -> {film_path}")
    print(f"Play it with:  open \"{film_path}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

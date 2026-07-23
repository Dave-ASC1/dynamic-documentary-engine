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

Shared logic (tracing, placeholder media generation) lives in
dde_runtime.py so this CLI script and the Flask backend (web/backend/app.py)
never drift apart on how a film is actually generated.

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
Version: 1.1.0
"""

import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from dde_runtime import (  # noqa: E402
    INDEX_PATH, METADATA_PATH, DEFAULT_ASSETS, DEFAULT_FILMS,
    art_map, label, dims, SelectionTracer, instrument_pairing, ensure_assets,
    load_usage_counts, merge_usage_counts, save_usage_counts,
    sync_media_library,
)
from engine import Sequencer, Assembler  # noqa: E402

BAR = "=" * 72


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
        print(f"  previous : {label(prev)}")

        ranking = ev["ranking"]
        if ranking:
            score_of = {id(a): s for a, s in ranking}
            print("  candidates by dissimilarity (higher = more unlike previous):")
            for a, s in ranking[:6]:
                mark = " <== CHOSEN" if a is chosen else ""
                print(f"      {s:>2}  {label(a)}{mark}")
            if len(ranking) > 6:
                print(f"      ... (+{len(ranking) - 6} more)")
            pool_ids = ", ".join(p.get("artifact_id") for p in ev["pool"])
            print(f"  juxtaposition pool (top candidates): {pool_ids}")
            chosen_score = score_of.get(id(chosen))
            print(f"  --> chose {label(chosen)}  (dissimilarity {chosen_score})")
            print(f"      contrast: {', '.join(dims(prev, chosen))}")
        else:
            print(f"  --> chose {label(chosen)}")
            print(f"      {dims(prev, chosen)[0]}")


def print_sequence(sequence, amap):
    print(f"\n{BAR}\nASSEMBLED FILM ORDER  ({len(sequence)} slots)\n{BAR}")
    total = 0.0
    for i, entry in enumerate(sequence):
        anchor = "  <-- generated opening" if i == 0 else (
            "  <-- generated closing" if i == len(sequence) - 1 else "")
        if isinstance(entry, tuple):
            b, x = entry
            bd = amap.get(b, {})
            xd = amap.get(x, {})
            dur = bd.get("duration_seconds", 0)
            total += dur
            print(f"  {i + 1:>2}. [B+X {dur:>4.0f}s]  {bd.get('title', b)}"
                  f"  +audio: {xd.get('title', x)}{anchor}")
        else:
            d = amap.get(entry, {})
            dur = d.get("duration_seconds", 0)
            total += dur
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
    ap.add_argument("--diversity", action="store_true",
                    help="Boost underused artifacts across rendered runs.")
    ap.add_argument("--pool-size", type=int, default=None,
                    help="Optional override for top-contrast candidate pool size.")
    ap.add_argument("--assets-path", default=DEFAULT_ASSETS)
    ap.add_argument("--films-path", default=DEFAULT_FILMS)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"{BAR}\nDYNAMIC DOCUMENTARY ENGINE — end-to-end validation run\n{BAR}")

    # Real media libraries get auto-synced against the index (new files
    # added, deleted files' entries dropped); the demo/ bootstrap path is
    # left alone since ensure_assets() below is what populates it.
    is_demo_mode = os.path.abspath(args.assets_path) == os.path.abspath(DEFAULT_ASSETS)
    if not is_demo_mode and os.path.isdir(args.assets_path):
        sync = sync_media_library(INDEX_PATH, args.assets_path)
        if sync["added"] or sync["removed"]:
            print(f"library sync : +{len(sync['added'])} added, "
                  f"-{len(sync['removed'])} removed (missing file)")

    usage_counts = load_usage_counts(args.films_path) if args.diversity else {}
    sequencer = Sequencer(
        INDEX_PATH,
        diversity_mode=args.diversity,
        usage_counts=usage_counts,
        juxtaposition_pool_size=args.pool_size,
    )
    loader = sequencer.loader
    amap = art_map(loader)
    coll = loader.collection

    counts = coll.get("artifact_counts", {})
    print(f"collection : {coll.get('collection_name')}  (id: {coll.get('collection_id')})")
    print(f"artifacts  : {counts.get('total')} total — "
          f"{counts.get('a_roll')} A-roll, {counts.get('b_roll')} B-roll, "
          f"{counts.get('x_roll')} X-roll")
    print("bookends   : generated per run from B-roll + X-roll body artifacts")
    print("diversity  : " + (
        "on — underused clips get a weight boost"
        if args.diversity else
        "off — strongest contrast candidates dominate"
    ))
    if args.pool_size:
        print(f"pool size  : top {args.pool_size} contrast candidates")
    elif args.diversity:
        print("pool size  : automatic — scales with available candidates")
    print(f"target     : {args.target}s"
          + (f"   (seed {args.seed})" if args.seed is not None else "   (unseeded)"))

    # Instrument, then generate through the real API.
    tracer = SelectionTracer(sequencer.selector)
    instrument_pairing(sequencer.selector, tracer)
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

    print(f"\n{BAR}\nRENDER — {'placeholder media' if is_demo_mode else 'real media'} -> film\n{BAR}")
    if is_demo_mode:
        stats = ensure_assets(loader, args.assets_path)
        print(f"  placeholder assets: {stats['created']} created, "
              f"{stats['existing']} already present")

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
    if args.diversity:
        updated = merge_usage_counts(usage_counts, sequencer.generated_usage)
        usage_path = save_usage_counts(args.films_path, updated)
        print(f"Diversity usage stats -> {usage_path}")
    print(f"Play it with:  open \"{film_path}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

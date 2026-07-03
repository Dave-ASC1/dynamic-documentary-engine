"""
build_validation_collection.py
------------------------------
Dynamic Documentary Engine — Validation Collection Builder

Generates a small, deliberately cross-category validation collection for
exercising the engine end to end before real media is added. Emits:

    metadata/validation/<artifact_id>.json      (one per artifact — full
                                                 metadata, valid against
                                                 artifact_schema.json)
    metadata/validation/validation_collection_index.json
                                                (the master index, valid
                                                 against collection_index_schema.json)

The collection is intentionally diverse (war, nature, industry, cosmos,
celebration, music, weather...) so adjacent clips have strong contrast for
the dissimilarity scorer to work with. This is a TEST FIXTURE, not a cap:
add more rows to SPECS as real media comes in.

WARNING — this generator emits the ORIGINAL placeholder bootstrap data.
The live collection in metadata/validation/ has since been hand-wired to
the real footage in local-media/assets/ (different filenames, durations,
and descriptions). Re-running this script would OVERWRITE that real-media
collection with these placeholder specs. To prevent accidental data loss,
main() refuses to overwrite an existing collection unless --force is
passed. Update SPECS to match the real media before ever using --force.

Each index entry is enriched with the top-level fields the engine actually
reads during selection (mood, pacing, tags, theme, dominant_lines,
geography, weight, can_repeat, must_not_follow, duration_seconds, title) —
because the sequencer scores against the index summary dicts, not the
individual artifact files.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import argparse
import json
import os

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
METADATA_DIR = os.path.join(REPO_ROOT, "metadata")
OUTPUT_DIR = os.path.join(METADATA_DIR, "validation")

ARTIFACT_SCHEMA_PATH = os.path.join(METADATA_DIR, "artifact_schema.json")
INDEX_SCHEMA_PATH = os.path.join(METADATA_DIR, "collection_index_schema.json")

INDEX_FILENAME = "validation_collection_index.json"

COLLECTION_ID = "validation"
COLLECTION_NAME = "Cross-Category Validation Collection"
COLLECTION_DESCRIPTION = (
    "A small, deliberately cross-category set of artifacts (war, nature, "
    "industry, cosmos, celebration, music, weather) used to validate the "
    "engine's juxtaposition sequencing end to end. Variety is the point: "
    "unlike clips maximise the contrast the selector is built to find."
)
CREATED_AT = "2026-07-02T00:00:00Z"

# ----------------------------------------------------------------------
# Artifact specifications — compact table, expanded to full JSON below.
# To grow the collection, add rows here. Fields:
#   id, type ('A-roll'|'B-roll'|'X-roll'), role ('body'),
#   dur (seconds), title, desc, theme[], mood, pacing, tags[], colors[],
#   lines, geo, weight, must_not_follow[]
# ----------------------------------------------------------------------

SPECS = [
    # --- A-roll (stand-alone, synchronized audio + video) ---
    dict(id="val_av_001", type="A-roll", role="body", dur=10,
         title="Empty highway at dawn",
         desc="A deserted desert highway stretches to the horizon as the sun rises. Faint wind and distant birds.",
         theme=["road", "dawn", "stillness"], mood="reflective", pacing="slow",
         tags=["exterior", "road", "sunrise", "quiet"], colors=["orange", "gray"],
         lines="horizontal", geo="Nevada", weight=0.5, must_not_follow=[]),

    dict(id="val_av_002", type="A-roll", role="body", dur=12,
         title="City skyline at night",
         desc="A dense city skyline pulses with light after dark, traffic streaming below. Ambient urban hum.",
         theme=["city", "night", "energy"], mood="hopeful", pacing="medium",
         tags=["cityscape", "lights", "night", "urban"], colors=["blue", "black"],
         lines="vertical", geo="Tokyo", weight=0.5, must_not_follow=[]),

    dict(id="val_av_003", type="A-roll", role="body", dur=14,
         title="Soldiers marching through ruins",
         desc="Black-and-white archival footage of infantry moving through a bombed-out town, distant artillery.",
         theme=["war", "soldiers", "destruction"], mood="somber", pacing="slow",
         tags=["archival", "black-and-white", "infantry", "war"], colors=["gray", "brown"],
         lines="horizontal", geo="France", weight=0.8, must_not_follow=[]),

    dict(id="val_av_004", type="A-roll", role="body", dur=9,
         title="Carnival crowd cheering",
         desc="A dense, colorful street carnival erupts in cheering and drums as dancers pass.",
         theme=["celebration", "crowd", "joy"], mood="triumphant", pacing="fast",
         tags=["color", "crowd", "festival", "motion"], colors=["red", "yellow"],
         lines="mixed", geo="Brazil", weight=0.7, must_not_follow=[]),

    dict(id="val_av_005", type="A-roll", role="body", dur=11,
         title="Storm waves strike a lighthouse",
         desc="Enormous waves crash over a coastal lighthouse in a gale; roaring surf and wind.",
         theme=["ocean", "storm", "power"], mood="urgent", pacing="fast",
         tags=["sea", "spray", "weather", "coast"], colors=["blue", "white"],
         lines="diagonal", geo="Ireland", weight=0.6, must_not_follow=[]),

    dict(id="val_av_006", type="A-roll", role="body", dur=16,
         title="Street violinist at dusk",
         desc="A lone violinist plays on an empty cobbled street as evening falls; solo strings and faint footsteps.",
         theme=["music", "solitude", "city"], mood="melancholic", pacing="slow",
         tags=["music", "portrait", "urban", "evening"], colors=["amber", "brown"],
         lines="vertical", geo="Vienna", weight=0.5, must_not_follow=[]),

    # --- Body: B-roll (video only — must always be paired with an X-roll) ---
    dict(id="val_bv_001", type="B-roll", role="body", dur=13,
         title="Time-lapse of storm clouds",
         desc="Fast time-lapse of towering storm clouds boiling across a wide sky.",
         theme=["sky", "weather", "time"], mood="tense", pacing="fast",
         tags=["timelapse", "clouds", "sky"], colors=["gray", "white"],
         lines="mixed", geo="Kansas", weight=0.6, must_not_follow=[]),

    dict(id="val_bv_002", type="B-roll", role="body", dur=15,
         title="Forest canopy from below",
         desc="Slow upward view through a towering forest canopy, light filtering through leaves.",
         theme=["nature", "forest", "calm"], mood="neutral", pacing="slow",
         tags=["trees", "green", "canopy", "nature"], colors=["green"],
         lines="vertical", geo="Oregon", weight=0.5, must_not_follow=["val_bv_001"]),

    dict(id="val_bv_003", type="B-roll", role="body", dur=12,
         title="Factory assembly line",
         desc="Robotic arms and conveyor belts move parts down a modern factory assembly line.",
         theme=["industry", "machines", "labor"], mood="neutral", pacing="medium",
         tags=["factory", "machinery", "industrial"], colors=["silver", "orange"],
         lines="horizontal", geo="Detroit", weight=0.5, must_not_follow=[]),

    dict(id="val_bv_004", type="B-roll", role="body", dur=18,
         title="Aurora over snow",
         desc="Green and violet aurora ripples above an empty snowfield under a star field.",
         theme=["cosmos", "night", "cold"], mood="hopeful", pacing="slow",
         tags=["aurora", "night", "arctic", "sky"], colors=["green", "purple"],
         lines="curved", geo="Norway", weight=0.7, must_not_follow=[]),

    # --- Body: X-roll (audio only — layered over B-roll, never stands alone) ---
    dict(id="val_xa_001", type="X-roll", role="body", dur=20,
         title="Distant thunder",
         desc="Low rolling thunder over faint rain — an ambient audio bed.",
         theme=["weather", "sound", "storm"], mood="tense", pacing="slow",
         tags=["thunder", "ambient", "storm"], colors=[],
         lines=None, geo="", weight=0.5, must_not_follow=[]),

    dict(id="val_xa_002", type="X-roll", role="body", dur=25,
         title="Cello drone",
         desc="A sustained, mournful cello drone with slow harmonic movement.",
         theme=["music", "drone", "melancholy"], mood="melancholic", pacing="slow",
         tags=["cello", "music", "drone"], colors=[],
         lines=None, geo="", weight=0.5, must_not_follow=[]),

    dict(id="val_xa_003", type="X-roll", role="body", dur=18,
         title="Marketplace chatter",
         desc="Overlapping voices, footsteps and clatter of a busy open-air market.",
         theme=["human", "voices", "city"], mood="neutral", pacing="fast",
         tags=["crowd", "voices", "ambient"], colors=[],
         lines=None, geo="", weight=0.5, must_not_follow=[]),

    dict(id="val_xa_004", type="X-roll", role="body", dur=22,
         title="Synth pulse",
         desc="A driving electronic synth pulse with rising tension.",
         theme=["electronic", "rhythm", "tension"], mood="urgent", pacing="fast",
         tags=["synth", "electronic", "pulse"], colors=[],
         lines=None, geo="", weight=0.6, must_not_follow=[]),
]

RUNTIME_RULES = {
    "min_duration_seconds": 45,
    "max_duration_seconds": 300,
    "allow_repeat_artifacts": False,
    "save_generated_films": True,
}


# ----------------------------------------------------------------------
# Expansion helpers
# ----------------------------------------------------------------------

def _format_for(spec):
    """Container format for the synthetic/real asset of this artifact."""
    return "wav" if spec["type"] == "X-roll" else "mp4"


def _filename_for(spec):
    return f"{spec['id']}.{_format_for(spec)}"


def _has_video(spec):
    return spec["type"] in ("A-roll", "B-roll")


def _has_audio(spec):
    return spec["type"] in ("A-roll", "X-roll")


def _source_for(spec):
    # Purely descriptive; synthetic placeholders stand in until real media lands.
    return "self-recorded"


def build_artifact_json(spec):
    """Expands a compact spec into a full artifact dict (artifact_schema.json)."""
    file_obj = {
        "source_type": "local",
        "filename": _filename_for(spec),
        "format": _format_for(spec),
        "duration_seconds": spec["dur"],
        "has_video": _has_video(spec),
        "has_audio": _has_audio(spec),
        "source": _source_for(spec),
        "copyright_cleared": True,
    }
    # Resolution only applies to artifacts that carry video.
    if _has_video(spec):
        file_obj["resolution"] = "640x360"

    content = {
        "title": spec["title"],
        "description": spec["desc"],
        "theme": spec["theme"],
        "mood": spec["mood"],
        "pacing": spec["pacing"],
        "tags": spec["tags"],
    }
    if spec.get("colors"):
        content["dominant_colors"] = spec["colors"]
    if spec.get("lines"):
        content["dominant_lines"] = spec["lines"]

    sequencing = {
        "can_repeat": False,
        "min_gap_seconds": 0,
        "must_follow": [],
        "must_not_follow": spec.get("must_not_follow", []),
        "weight": spec["weight"],
    }

    return {
        "artifact_id": spec["id"],
        "collection_id": COLLECTION_ID,
        "artifact_type": spec["type"],
        "role": spec["role"],
        "file": file_obj,
        "content": content,
        "sequencing": sequencing,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


def build_index_entry(spec):
    """Builds an enriched collection-index summary entry for an artifact.

    Carries the top-level fields the engine reads during selection — the
    sequencer scores against these summary dicts, not the individual files.
    """
    entry = {
        "artifact_id": spec["id"],
        "artifact_type": spec["type"],
        "role": spec["role"],
        "filename": _filename_for(spec),
        "duration_seconds": spec["dur"],
        # Enrichment used by the selector / rules:
        "title": spec["title"],
        "mood": spec["mood"],
        "pacing": spec["pacing"],
        "tags": spec["tags"],
        "theme": spec["theme"],
        "weight": spec["weight"],
        "can_repeat": False,
        "must_not_follow": spec.get("must_not_follow", []),
    }
    if spec.get("lines"):
        entry["dominant_lines"] = spec["lines"]
    if spec.get("geo"):
        entry["geography"] = spec["geo"]
    return entry


def build_index():
    counts = {"total": len(SPECS), "a_roll": 0, "b_roll": 0, "x_roll": 0}
    key = {"A-roll": "a_roll", "B-roll": "b_roll", "X-roll": "x_roll"}
    for s in SPECS:
        counts[key[s["type"]]] += 1

    return {
        "collection_id": COLLECTION_ID,
        "collection_name": COLLECTION_NAME,
        "description": COLLECTION_DESCRIPTION,
        "version": "1.0.0",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "runtime_rules": RUNTIME_RULES,
        "artifact_counts": counts,
        "artifacts": [build_index_entry(s) for s in SPECS],
    }


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

def _validate(instance, schema_path, label):
    try:
        import jsonschema
    except ImportError:
        print(f"  ! jsonschema not installed — skipped validating {label}")
        return True
    with open(schema_path, "r") as f:
        schema = json.load(f)
    try:
        jsonschema.validate(instance=instance, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        print(f"  X SCHEMA ERROR in {label} at {loc}: {e.message}")
        return False


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate the placeholder validation collection. "
                    "Refuses to overwrite an existing collection unless --force."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing collection in metadata/validation/. "
             "DANGER: this replaces the hand-wired real-media collection with "
             "the placeholder SPECS in this file. See the module docstring."
    )
    args = parser.parse_args()

    index_path = os.path.join(OUTPUT_DIR, INDEX_FILENAME)
    if os.path.exists(index_path) and not args.force:
        print(
            "Refusing to overwrite the existing collection at "
            f"{os.path.relpath(OUTPUT_DIR, REPO_ROOT)}/.\n"
            "The live collection is hand-wired to real media; re-running this "
            "generator would replace it with placeholder data.\n"
            "If you really intend to regenerate from the placeholder SPECS in "
            "this file, pass --force."
        )
        return 1

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_valid = True

    print(f"Building validation collection -> {os.path.relpath(OUTPUT_DIR, REPO_ROOT)}/")
    print(f"  {len(SPECS)} artifacts\n")

    # Individual artifact files
    for spec in SPECS:
        artifact = build_artifact_json(spec)
        path = os.path.join(OUTPUT_DIR, f"{spec['id']}.json")
        with open(path, "w") as f:
            json.dump(artifact, f, indent=2)
            f.write("\n")
        ok = _validate(artifact, ARTIFACT_SCHEMA_PATH, f"{spec['id']}.json")
        all_valid = all_valid and ok
        print(f"  {'ok' if ok else 'XX'}  {spec['id']:<14} {spec['type']:<7} {spec['role']:<8} {spec['title']}")

    # Collection index
    index = build_index()
    index_path = os.path.join(OUTPUT_DIR, INDEX_FILENAME)
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
    ok = _validate(index, INDEX_SCHEMA_PATH, INDEX_FILENAME)
    all_valid = all_valid and ok
    print(f"\n  {'ok' if ok else 'XX'}  {INDEX_FILENAME}")

    print("\n" + ("All files valid against their schemas." if all_valid
                  else "SCHEMA VALIDATION FAILED — see errors above."))
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

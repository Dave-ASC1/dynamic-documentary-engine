# Handoff — Dynamic Documentary Engine

Last updated: 2026-07-03

## Current Summary

Dynamic Documentary Engine is now an end-to-end generative documentary prototype. It loads local media metadata, generates a film sequence, pairs B-roll with X-roll audio where needed, renders a playable MP4 with FFmpeg, and saves review outputs locally.

No external generation services are used at runtime. The sequencing is rule-based creative code driven by metadata, contrast scoring, weights, and optional diversity tracking.

Current artifact model:

- **A-roll**: video with synchronized audio; can stand alone.
- **B-roll**: visual/video material; never stands alone.
- **X-roll**: audio-only; layered under B-roll.
- **B+X slot**: one B-roll video paired with one X-roll audio track; counts as one screen-time slot.

Current generation behavior:

- Opening is no longer fixed. The engine generates a randomized **B-roll + X-roll** opening from body artifacts.
- Closing is no longer fixed. The engine reserves and appends a randomized **B-roll + X-roll** closing.
- Body picks come from any eligible A-roll or B-roll.
- X-roll is never selected as standalone footage.
- B-roll always receives X-roll audio.
- The selector favors juxtaposition: it ranks candidates by contrast against the previous visual artifact.

## What Changed Recently

Recent updates implemented and tested:

- Real media in `local-media/assets/` is wired into the validation metadata.
- Validation artifacts now reference actual uploaded files, not placeholder filenames.
- Fixed opening/closing A-roll was removed.
- `val_av_001` and `val_av_002` are now regular body clips, not structural bookends.
- Generated films now open and close with randomized B-roll/X-roll pairs.
- A-roll and B-roll compete together in the body selection pool.
- The first body pick is compared against the generated opening B-roll, so it is also contrast-driven.
- The assembler normalizes mixed media to `1280x720`, `30fps`, H.264/AAC before concatenation.
- Diversity mode was added.
- Diversity mode now uses an automatic candidate pool that scales with the available footage instead of a fixed small pool.
- Cross-render usage history is saved to `local-media/films/usage_stats.json`.

## Current Run Command

Recommended command for real local media:

```bash
cd "/Users/kingdavid/documentary engine/dynamic-documentary-engine"

python3 scripts/run_first_film.py --target 60 --runs 0 --diversity --assets-path local-media/assets --films-path local-media/films
```

Notes:

- `--target 60` asks for about a 60-second film.
- `--runs 0` skips extra text-only preview generations.
- `--diversity` boosts underused clips across rendered runs.
- No `--pool-size` is needed anymore. Diversity mode scales the pool automatically.
- Output MP4s are saved to `local-media/films/`.

## Target Duration Behavior

The requested target duration is approximate right now.

Why:

- The sequencer works with whole artifacts.
- If the film is at 28 seconds and the next selected clip is 9 seconds, the output can become 37 seconds.
- If the user requests 240 seconds but the collection only has about 97 seconds of non-repeating visual footage, the engine stops when eligible visual material runs out.
- X-roll does not add screen time because it plays underneath B-roll.

Current behavior:

```text
Target duration = goal
Rendered duration = nearest generated sequence using whole clips
```

Potential future improvement:

- Add exact-duration mode where the final clip is trimmed to land exactly on the requested timestamp.

## Slot Count Behavior

There is no hard 10-slot limit.

The current validation collection has 10 visual clips:

- 6 A-roll
- 4 B-roll

Because repeats are disabled, a generated film can only use so many visual slots before it runs out of eligible footage. X-roll does not count as an additional visual slot because it plays under B-roll.

To create longer or more varied films:

- Add more A-roll and B-roll footage.
- Allow repeats.
- Allow B-roll to repeat with different X-roll pairings.
- Add exact-duration or excerpt support.

## Diversity Mode

Problem observed:

- The engine was technically randomized, but it often felt like the same clips were being rearranged.
- Some clips appeared repeatedly because they scored highly for contrast.
- Other clips rarely entered the old tight top-3 selection pool.

Current solution:

- Normal mode keeps the historical tight top-3 contrast pool.
- Diversity mode widens the pool automatically.
- Diversity mode still ranks by contrast first.
- Underused clips receive a weight boost using persisted usage counts.
- Usage is tracked across rendered films in:

```text
local-media/films/usage_stats.json
```

Important:

- Usage stats update only when a film is actually rendered.
- `--no-render` preview runs do not update usage history.

Current diversity command:

```bash
python3 scripts/run_first_film.py --target 60 --runs 0 --diversity --assets-path local-media/assets --films-path local-media/films
```

Optional experimental override:

```bash
--pool-size N
```

This still exists, but the recommended path is to omit it and let diversity mode scale automatically.

## Current Validation Collection

The validation collection lives at:

```text
metadata/validation/validation_collection_index.json
metadata/validation/val_*.json
```

It is wired to real files under:

```text
local-media/assets/
├── a-roll/
├── b-roll/
└── x-roll/
```

Current collection counts:

```text
14 total artifacts
6 A-roll
4 B-roll
4 X-roll
```

Current real media examples:

- `a-roll/First_skate.mov`
- `a-roll/SF_Zoo.MOV`
- `a-roll/chick_stir_fry.mov`
- `a-roll/robotic_arm.mov`
- `a-roll/gallery_monkey.mov`
- `a-roll/skate_boarding.mov`
- `b-roll/warship_cruising.mp4`
- `b-roll/waves_sunset.mp4`
- `b-roll/plane_drop.mp4`
- `b-roll/colorful_ballerina.mp4`
- `x-roll/piano_sound.wav`
- `x-roll/water_stream.wav`
- `x-roll/war_bong.wav`
- `x-roll/birds_call.wav`

## Latest Verified Test

The latest tested command was:

```bash
python3 scripts/run_first_film.py --target 60 --runs 0 --diversity --assets-path local-media/assets --films-path local-media/films
```

Test result:

- Python compile passed.
- JSON schema validation passed.
- Trace-only diversity run passed.
- Full FFmpeg render passed.
- Output MP4 was verified with `ffprobe`.

Latest verified output:

```text
local-media/films/film_validation_20260703_140620_466e.mp4
```

Verified media properties:

```text
duration: 67.64s
video:    H.264, 1280x720, 30fps
audio:    AAC stereo, 48000 Hz
```

## Important Commands

Compile check:

```bash
python3 -m compileall engine scripts
```

Schema validation:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft7Validator

root = Path('/Users/kingdavid/documentary engine/dynamic-documentary-engine')
collection_schema = json.loads((root/'metadata/collection_index_schema.json').read_text())
artifact_schema = json.loads((root/'metadata/artifact_schema.json').read_text())
collection = json.loads((root/'metadata/validation/validation_collection_index.json').read_text())

errors = []
errors.extend(('collection', e) for e in Draft7Validator(collection_schema).iter_errors(collection))
for path in sorted((root/'metadata/validation').glob('val_*.json')):
    doc = json.loads(path.read_text())
    errors.extend((path.name, e) for e in Draft7Validator(artifact_schema).iter_errors(doc))

if errors:
    for name, err in errors:
        print(f'{name}: {"/".join(map(str, err.path))}: {err.message}')
    raise SystemExit(1)

print('schema validation passed')
PY
```

Render one real film:

```bash
python3 scripts/run_first_film.py --target 60 --runs 0 --diversity --assets-path local-media/assets --films-path local-media/films
```

Render without diversity:

```bash
python3 scripts/run_first_film.py --target 60 --runs 0 --assets-path local-media/assets --films-path local-media/films
```

Preview sequence only:

```bash
python3 scripts/run_first_film.py --target 60 --runs 3 --no-render --diversity --assets-path local-media/assets --films-path local-media/films
```

## FFmpeg Behavior

FFmpeg is installed and working:

```text
FFmpeg: /opt/homebrew/bin/ffmpeg
Version observed: 8.1.2
```

Assembler behavior:

- A-roll is rendered directly with its own audio.
- B-roll + X-roll is rendered as one segment.
- If X-roll is longer than B-roll, audio is cut at the B-roll end.
- If X-roll is shorter than B-roll, audio loops until the B-roll ends.
- All segments are normalized before final concatenation.
- Final output is MP4.

## Local Media / Output Folders

Current real-media workspace:

```text
local-media/
├── raw/
├── assets/
│   ├── a-roll/
│   ├── b-roll/
│   └── x-roll/
└── films/
```

Use:

- `local-media/raw/`: original downloads or recordings before cleanup.
- `local-media/assets/`: engine-ready clips referenced by metadata.
- `local-media/films/`: generated review films and diversity usage stats.

The actual media files are ignored by Git. Do not delete user media.

## Current Git / Repo Notes

At last check, there were uncommitted modifications to:

```text
AGENT.md
engine/artifact_selector.py
engine/sequencer.py
scripts/dde_runtime.py
scripts/run_first_film.py
handoff.md
```

There is also local generated media/output under `local-media/`.

No commit or push was made. If committing later, use the user’s branch workflow and ask before any repository action.

Standing branch guidance from earlier notes:

- Work should go to `first-run-demo` first.
- Do not commit, push, merge, or otherwise move anything to `main` without explicit user authorization.
- Do not silently push.

## Conversation / Meeting Talking Points

Informal update version:

> Since last time, the engine can actually render playable MP4 films from local media. It chooses A-roll or B-roll automatically, pairs B-roll with audio, generates opening and closing B-roll/audio pairs, and saves review films locally. I also added diversity mode because the first version kept favoring the same high-contrast clips. Now it still respects contrast, but it explores more of the collection and gives underused clips a better chance.

Potential professor questions:

- What changed since last time?
- Is it random or rule-based?
- How does it decide what clip comes next?
- What does B+X mean?
- Why is the duration approximate?
- Why did a 240-second request only make about 97 seconds?
- Why did a 30-second request make 37 seconds?
- Why did some clips repeat across multiple renders?
- What does diversity mode change?
- What is still manual?
- What is the next improvement?

Short answers:

- It is controlled randomness, not pure shuffle.
- Metadata contrast drives ordering.
- Diversity mode reduces overuse of the same clips.
- Duration is approximate because the engine currently preserves whole artifacts.
- Longer requested films require more visual footage or repeats.
- Metadata is still manual.
- Next upgrades could be exact-duration trimming, excerpt support, a richer media collection, and a simple review interface.

## Recommended Next Steps

1. Generate several films with diversity mode on and review whether the clips feel more varied.
2. Add more A-roll and B-roll footage, because visual footage is the current limit on longer films.
3. Consider exact-duration mode so `--target 30` renders exactly 30 seconds.
4. Consider excerpt support for using random windows from longer source clips.
5. Add a simple UI or env-var support so the web app can generate from `local-media/assets` without Terminal commands.
6. Keep improving metadata quality; the engine’s decisions are only as good as the metadata.

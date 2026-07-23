# Handoff — Dynamic Documentary Engine

Last updated: 2026-07-23

## Current Summary

Dynamic Documentary Engine is a fully functional end-to-end generative documentary system. It loads local media metadata, generates unique film sequences using contrast-driven selection, pairs B-roll with X-roll audio, and renders playable MP4s with FFmpeg. The system includes both a command-line interface and a web UI for turnkey operation.

No external generation services are used at runtime. All sequencing is rule-based creative code driven by metadata, dissimilarity scoring, artifact weights, and optional diversity mode for collection exploration.

Current artifact model:

- **A-roll**: video with synchronized audio; can stand alone.
- **B-roll**: visual/video material; never stands alone.
- **X-roll**: audio-only; layered under B-roll as soundtrack.
- **B+X slot**: one B-roll video paired with one X-roll audio; counts as one screen-time slot.

Current generation behavior:

- Opening: randomized **B-roll + X-roll** pair from body artifacts.
- Closing: randomized **B-roll + X-roll** pair reserved before body selection.
- Body picks: A-roll or B-roll, competing in the same pool.
- X-roll: strictly paired with B-roll; never selected as standalone.
- Selection criterion: maximum dissimilarity (contrast) from the previous visual artifact.
- Diversity mode: boosts underused clips via cross-run usage tracking to prevent oversaturation of high-contrast favorites.

## What Changed (2026-07-23)

Latest verified updates:

- **Web UI is production-ready**: Flask backend running, frontend serving at `http://127.0.0.1:5000`.
- **Real media collection complete**: 13 clips recovered and organized (5 A-roll, 4 B-roll, 4 X-roll).
- **Simple film naming**: Switched from `film_validation_YYYYMMDD_HHMMSS_xxxx.mp4` to sequential `film_test_1.mp4`, `film_test_2.mp4`, etc.
- **X-roll standalone bug fixed**: X-roll artifacts (audio-only) can no longer be selected as primary picks, eliminating green-screen-with-beep artifacts.
- **Web UI tested end-to-end**: Generated films play in browser with full contrast reasoning trace and history.
- **Media recovery**: All 13 media files salvaged from system Trash and restored to `local-media/assets/`.

## Current Media Collection

Validated and tested with real footage:

```
local-media/assets/
├── a-roll/          (5 files, 99M)
│   ├── First_skate.mov
│   ├── chick_stir_fry.mov
│   ├── gallery_monkey.mov
│   ├── robotic_arm.mov
│   └── skate_boarding.mov
├── b-roll/          (4 files, 52M)
│   ├── colorful_ballerina.mp4
│   ├── plane_drop.mp4
│   ├── warship_cruising.mp4
│   └── waves_sunset.mp4
└── x-roll/          (4 files, 9.8M)
    ├── birds_call.wav
    ├── piano_sound.wav
    ├── war_bong.wav
    └── water_stream.wav
```

Total: **13 clips, 160M**, wired to validation metadata.

## Recommended Commands

Web UI (local testing):

```bash
cd "/Users/kingdavid/documentary engine/dynamic-documentary-engine"
python3 web/backend/app.py
# Open http://127.0.0.1:5000 in browser
```

CLI with diversity (when not using web UI):

```bash
python3 scripts/run_first_film.py --target 60 --runs 0 --diversity \
  --assets-path local-media/assets --films-path local-media/films
```

## Web UI Features

- **Generate button**: Triggers film generation with target duration input.
- **Video player**: Plays rendered film directly in the browser.
- **Sequence trace**: Shows all cuts with dissimilarity scoring and contrast reasoning for each transition.
- **Film history**: Lists all previously generated films with links to play.
- **Status messages**: Reports generation progress ("Done.").

## Exhibit Deployment (Next Phase)

Planned for local-network kiosk mode:

1. **Hardware**: Mac Mini or Raspberry Pi at the exhibit.
2. **Network**: Flask runs on the machine; Dr. Campbell accesses via `http://[machine-ip]:5000` from any browser.
3. **Media**: OneDrive Desktop Sync will sync `media-file/` folder to the exhibit machine's local storage.
4. **Workflow**: Dr. Campbell clicks "Generate" → film renders in ~30 seconds → plays automatically.

### Still TODO

- [ ] Add diversity mode toggle to web UI (checkbox).
- [ ] Test web UI with diversity enabled.
- [ ] Configure OneDrive Desktop Sync on exhibit machine.
- [ ] Set Flask to auto-start on boot.
- [ ] Test local network access (`http://[machine-ip]:5000`).
- [ ] Create quick-start guide for Dr. Campbell (no Terminal, no code).

## Latest Verified Test

**Test date**: 2026-07-23  
**Command**: Web UI generate button (default 90s target)  
**Result**: ✅ PASS

- Film generated: `film_test_1.mp4` (97s)
- Media used: Real clips (Plane drop, Robotic arm, Chicken stir fry, Waves sunset, First skate, Warship, San Francisco zoo, Gallery monkey, Skate boarding, Colorful ballerina).
- Video player: ✅ Plays in browser
- Sequence trace: ✅ Full contrast reasoning displayed
- X-roll: ✅ No standalone selections (only paired with B-roll)

## Architecture Overview

```
Web UI (browser)
    ↓
Flask Backend (app.py)
    ↓
dde_runtime.py (shared generation logic)
    ↓
Sequencer (generate)  →  loads collection, builds contrast-ranked sequence
    ↓
Assembler (render)    →  pairs B+X, normalizes media, renders MP4
    ↓
FFmpeg                →  H.264 video, AAC stereo, 1280x720, 30fps
    ↓
local-media/films/    →  film_test_1.mp4, film_test_2.mp4, etc.
```

## Important Files

- **Backend**: `web/backend/app.py` — Flask API
- **Frontend**: `web/frontend/index.html`, `app.js`, `style.css`
- **Engine**: `engine/sequencer.py`, `engine/artifact_selector.py`, `engine/rules.py`, `engine/assembler.py`
- **Metadata**: `metadata/validation/validation_collection_index.json`, `metadata/validation/val_*.json`
- **Media**: `local-media/assets/a-roll/`, `local-media/assets/b-roll/`, `local-media/assets/x-roll/`
- **Output**: `local-media/films/` (generated MP4s and manifests)

## Key Design Decisions

1. **No emotional continuity**: Juxtaposition and contrast drive all sequencing decisions. Mood and pacing metadata are scored dimensions, not enforcement rules.
2. **Diversity mode is optional**: Normal mode keeps a tight top-3 contrast pool (strongest cuts). Diversity mode widens the pool and boosts underused clips for broader collection exploration.
3. **X-roll paired, never standalone**: Audio-only clips are always paired with B-roll video; they cannot be selected independently.
4. **Sequential naming for exhibits**: Films are named `film_test_1.mp4`, `film_test_2.mp4`, etc., for easy reference in a kiosk setting.
5. **Local-network architecture**: No cloud dependencies; media stays on the exhibit machine or OneDrive-synced local storage.

## Conversation & Talking Points

**For Dr. Campbell (non-technical)**:

> "The engine generates a different film every time you click 'Generate'. It picks clips from your media collection and arranges them so consecutive clips contrast as much as possible — different moods, different locations, different subjects. It's designed to surprise and engage viewers, not comfort them. You can click as many times as you want; each film is unique."

**For academic/technical audiences**:

- How does the engine differ from traditional documentary editing? (No emotional arc, pure contrast maximization.)
- What happens if the same clips appear in multiple generated films? (Diversity mode prevents oversaturation; usage counts persist across runs.)
- Why B-roll + X-roll pairing? (B-roll is visual-only; X-roll provides layered audio without adding screen time.)
- How does it ensure variety in a small collection? (Dissimilarity scoring + diversity mode + weighted randomness within contrast pool.)

## Next Steps

1. Finish web UI (add diversity toggle).
2. Test exhibit setup (local network access on Mac Mini).
3. Integrate OneDrive (media management from the cloud folder).
4. Deploy and validate with Dr. Campbell.
5. Document for unattended operation.

## Recommended Test Flow

1. Generate 5–10 films via web UI.
2. Review sequence traces for contrast reasoning.
3. Check that no clip repeats (or follows expected repeat rules).
4. Verify audio sync and video quality.
5. Test diversity mode (if implemented) for visible clip variety.
6. Simulate exhibit kiosk mode (browser fullscreen, single button to generate).

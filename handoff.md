# Handoff — Dynamic Documentary Engine

Last updated: 2026-08-17

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
- **Fixed opening title card and closing credits card** wrap every film (see below) — separate from the randomized B+X bookends above, which is *within* the dynamic sequence, not the fixed cards around it.

## What Changed (2026-08-17)

Three items from the 2026-08-17 meeting with Dr. Campbell, plus two audio
defects found and fixed afterwards.

**1. Why audio and video sometimes cut together and sometimes don't — root cause, now fixed**

Dr. Campbell noticed the sound sometimes changes at the same moment the
picture does, and sometimes seems to change on its own. The controlling
factor is **the X-roll's length versus the B-roll it's paired with** —
nothing to do with the toggles, which only change it indirectly.

In a B+X slot the video comes from the B-roll and the audio from the
X-roll, and FFmpeg is told to loop the audio (`-stream_loop -1`) and cut at
the video's end (`-shortest`). So:

- **X-roll longer than the B-roll** → one unbroken slice of audio runs under
  the clip and ends with it. Sound and picture change **together**.
- **X-roll shorter than the B-roll** → the audio runs out mid-clip and
  restarts from the beginning while the picture keeps going. That restart
  is heard as the sound "changing" on its own, with no cut on screen.

Confirmed by rendering `war_bong.wav` (6.6s) under `warship_cruising.mp4`
(10.09s) and hashing the result: the audio at 6.616s is byte-for-byte
identical to the audio at 0s — it is provably the same audio starting over.

In the current Validation set this affects `war_bong.wav` (6.6s) under
almost every B-roll, and `piano_sound.wav` (10.105s) under
`drawn_animation.MOV` (10.548s). The two long MP3s (194s and 141s) never
loop, which is why clips using them always look in sync.

Why it seemed tied to the "exact duration" toggle: that toggle changes how
the sequence is composed (the closing clip's runtime is only reserved from
the budget when it's off) and trims the tail when it's on. Either shifts
which clips land where, changing the odds of hitting a short-X-roll/long-
B-roll pairing — but it isn't the cause.

**Fixed**, without putting any restriction on which audio can pair with
which clip — that mattered, because requiring audio to be at least as long
as the clip would have undone the random-excerpt behaviour above.

Instead of looping, the audio bed is now built from **several excerpts, each
taken from its own random point in the file, handed over with a short
(0.4s) crossfade**. A 6.6-second sound under a 10-second clip now plays two
different excerpts back to back rather than the same one twice. Nothing
repeats within a slot, the seam is inaudible, and any audio file still works
under any clip.

Verified on the original failing case: the audio at 6.616s used to be
byte-for-byte identical to the audio at 0s; it no longer is, the bed runs
continuously with no dropout, and segment durations are unchanged from
before.

One safety net: if a sound is so short relative to the clip that it would
need more than 24 excerpts (say a 0.3s sound under a minute of video), it
falls back to plain looping. Repetitive, but it covers the clip — B-roll is
never left silent.

**1b. Audio bleeding across cuts — separate cause, and this one IS fixed**

A second, unrelated defect, found after David reported hearing sound bleed
across cuts. This one was not about clip lengths at all.

The final film was assembled with FFmpeg's concat *demuxer* using `-c copy`,
which splices the already-encoded segments at the container level without
re-encoding. An AAC audio frame is 1024 samples, so each segment's final
frame is padded and each carries its own priming samples. Stream-copying
leaves all of that in place at every join, so roughly **the last 50ms of each
clip's audio kept playing at full volume over the start of the next clip**.

Measured on a test where a tone clip is followed by a digitally silent one:
the silent clip's first 20ms came back at **-24 dBFS** — the tone's full
level — instead of silence.

Fixed by assembling with the concat *filter* instead, which decodes every
segment and re-encodes one continuous stream so timestamps stay monotonic
across each join. Same measurement after the fix: **-71 dBFS**, i.e.
inaudible. This is the identical approach the title-card wrap already used,
and for the same reason — the main assembly had just never been switched
over.

Worth being precise about one thing: this bleed happened on **every** film,
with the "exact duration" toggle on or off. Re-encoding during the trim does
*not* clean it up — once the bleed is spliced into the audio, re-encoding
faithfully reproduces it (verified). So the toggle was never what controlled
it; it was present the whole time and is now gone in all cases.

Side effect: assembly now re-encodes rather than copies, so rendering is
somewhat slower. A 45-second film takes about 12 seconds to render.

**2. Cancel button** — the web UI can now stop a render in progress. Because
generation time is almost entirely FFmpeg, cancelling also kills the FFmpeg
process actually running, so it stops within a second or two instead of
after the current clip finishes. A cancelled run reports "Generation
cancelled", not an error.

**3. Per-genre opening/closing pieces** — these are no longer hard-coded.
Every topic folder now has `titles/opening/` and `titles/closing/`. Drop a
video into either and it becomes that topic's opening or closing piece, at
whatever length it is (a WWII opener can run minutes; a Swiss one can be
seconds). Leave a folder empty and the standard generated text card is used
instead. Files of any resolution, frame rate, or codec are accepted, with or
without their own audio — the engine letterboxes and re-times them to match
the film. Each folder has a README.txt explaining this in plain language.

Also: the web server's default port moved from 5000 to **5001**, because
macOS runs AirPlay Receiver on 5000 and silently takes the port. Set the
`PORT` environment variable to override.

## What Changed (2026-07-23)

This was a large working session — engine fixes, a full frontend rebuild, and a real architecture change requested live by Dr. Campbell. In order:

**Engine / duration handling**
- **Fixed a real overshoot bug**: the closing B+X bookend's duration wasn't checked against the target budget at all, so films reliably ran ~5–10s over the requested length. Now the closing clip's duration is reserved in the budget before body selection runs, so whole-clip sequences never exceed `target_duration`.
- **Added "exact duration" mode** (opt-in): lets the sequence run past target using whole clips, then trims the final render down to the exact requested length. Off by default (never cuts real footage; may land a few seconds short). Verified frame-accurate via re-encoding, not stream-copy.
- **Auto-sync media library**: the engine now scans each collection's `assets/` folders on every generate call. Drop a file in → it's auto-tagged (duration, dominant color, pacing heuristic) and enters rotation. Delete a file → its index entry is retired automatically instead of ever regenerating a placeholder for it. This is what fixed the earlier green-screen-placeholder (`SF_Zoo.MOV`) bug for good.

**Fixed opening/closing cards (per Dr. Campbell)**
- Every generated film now opens on a **title card** ("Welcome to the Dynamic Documentary Engine" + Faculty Supervisor: Dr. Betsy Campbell / Created by: Oluwafemisola David Ademoye / Collaborator: Omotola Ajibike Ajao) and closes on an **end card** ("The End" / "Thanks for watching"). Rendered via Pillow (the installed ffmpeg build has no `drawtext` filter) using the site's own Georgia serif typography, then concatenated around the render. Not counted toward `target_duration` — exact-duration mode accounts for the ~10s the cards add so the *whole file* still lands on target.

**Multi-topic collections (architecture change)**
- Per Dr. Campbell's direction from the 2026-07-23 planning meeting: each film topic (World War II, Swiss, ...) now gets its own self-contained folder instead of one shared pool — see **Media Collection** below.
- The engine auto-discovers any `local-media/<Name>/` folder shaped like `assets/` + `artifacts/` and auto-creates a schema-valid metadata index for it the first time it's seen — no code changes needed to add a new topic.
- Web UI now has a **Film Topic** selector; generating from an empty topic is blocked with a clear message instead of erroring.

**Frontend rebuild**
- Full cinematic redesign: hero section, framed video player, color-coded contrast timeline, card-grid film history (replacing the original plain layout).
- **Penn State branding**: official colors (Nittany Navy `#001E44`, Beaver Blue `#1e407c`), official PSU logo (top-left, links to ist.psu.edu), institutional wording.
- **Light/dark theme toggle** (moon/sun icon, top-right), persisted via `localStorage`. Light = PSU white/navy; dark = original cinematic near-black theme. Both fully maintained, not one replacing the other.
- Decorative header bars restyled as solid black filmstrip perforation strips (not theme-dependent, like the video screen frame).
- **Diversity mode** and **exact duration** toggles added to the UI with hover-tooltip explanations, centered layout.
- **Delete button** on film history entries (`DELETE /api/films/<collection>/<filename>`).
- Backend now binds to `0.0.0.0` (not just `127.0.0.1`) so it's reachable over the local network / a tunnel, not just from the same machine — this is what let Dr. Campbell test it remotely via a Cloudflare tunnel during the planning meeting.

**Verified in a live meeting**: Dr. Campbell generated and reviewed films herself (45s target, diversity + exact duration both on) over a Cloudflare tunnel during a working session on 2026-07-23. She confirmed satisfaction with progress.

## Current Media Collection

**New structure as of 2026-07-23** — each film topic is self-contained:

```
local-media/
├── Validation/                          (13 real clips — original test/demo set)
│   ├── assets/
│   │   ├── a-roll/   (5 files: First_skate, chick_stir_fry, gallery_monkey, robotic_arm, skate_boarding)
│   │   ├── b-roll/   (4 files: colorful_ballerina, plane_drop, warship_cruising, waves_sunset)
│   │   └── x-roll/   (4 files: birds_call, piano_sound, war_bong, water_stream)
│   ├── titles/
│   │   ├── opening/  (drop a video here → this topic's opening piece)
│   │   └── closing/  (drop a video here → this topic's closing piece)
│   └── artifacts/    (rendered films + manifests + usage_stats.json)
├── WWII/                                (empty — waiting on Betsy's footage)
│   ├── assets/{a-roll,b-roll,x-roll}/
│   ├── titles/{opening,closing}/
│   └── artifacts/
└── SWISS/                               (empty — waiting on footage)
    ├── assets/{a-roll,b-roll,x-roll}/
    ├── titles/{opening,closing}/
    └── artifacts/
```

**To give a topic its own opening/closing:** put one video file in
`local-media/<Topic>/titles/opening/` (and/or `closing/`). Any length,
any format. An empty folder falls back to the standard generated text card.

Each topic has its own metadata index at `metadata/collections/<topic>_collection_index.json` (auto-created for new topics). **To add a topic**: create `local-media/<Name>/assets/{a-roll,b-roll,x-roll}/` and `local-media/<Name>/artifacts/` — the engine and web UI pick it up automatically, no code or settings needed. **To add footage to an existing topic**: drop files into the right `assets/<roll-type>/` subfolder — auto-detected on next generate.

## Recommended Commands

Web UI (local testing):

```bash
cd "/Users/kingdavid/documentary engine/dynamic-documentary-engine"
python3 web/backend/app.py
# Open http://127.0.0.1:5001 in browser (or http://<machine-ip>:5001 from another device on the same network)
```

CLI, against a specific topic's footage (bypasses the web UI's topic selector):

```bash
python3 scripts/run_first_film.py --target 60 --runs 0 --diversity \
  --assets-path "local-media/Validation/assets" --films-path "local-media/Validation/artifacts"
```

## Web UI Features

- **Film topic selector**: choose which collection (World War II, Swiss, Validation, ...) to generate from; disabled with a clear message if the topic has no footage yet.
- **Generate button**: triggers film generation with target duration input.
- **Diversity mode toggle**: boosts underused clips across runs.
- **Exact duration toggle**: trims the final render to match the target length precisely.
- **Light/dark theme toggle**: PSU-branded light theme or cinematic dark theme, remembered across visits.
- **Video player**: plays the rendered film (with fixed intro/outro cards) directly in the browser.
- **Sequence trace**: shows all cuts with dissimilarity scoring and contrast reasoning for each transition.
- **Film history**: lists previously generated films per topic, with delete buttons.
- **Sync notice**: banner when the media library auto-detects new or retired clips.
- **Status messages**: reports generation progress ("Done.").

## Exhibit Deployment (Next Phase)

Discussed with Dr. Campbell on 2026-07-23: leaning toward an **old loaner laptop from Penn State IT** rather than buying new hardware, running behind the scenes with output on a wall-mounted screen. Open question still to resolve with her: whether gallery staff start longer films manually, or visitors trigger shorter films via a simple button interface.

1. **Hardware**: Penn State IT loaner laptop (per Betsy's suggestion) — David to follow up with Penn State IT.
2. **Network**: Flask now binds to `0.0.0.0`, so it's already reachable via `http://[machine-ip]:5001` from any device on the same network — no further backend change needed for this.
3. **Media**: still planned to sync footage via OneDrive to the exhibit machine's local storage; not yet tested end-to-end.
4. **Workflow**: click "Generate" → film renders (title card + dynamic sequence + end card) → plays automatically.
5. **Hosting for remote testing**: currently using a temporary Cloudflare quick tunnel for remote demos (e.g., the 2026-07-23 meeting with Dr. Campbell) — not meant to be permanent. Next step is connecting with Penn State IT about a safer, Penn State-managed way to host (e.g., something OneDrive-adjacent) instead of relying on Cloudflare long-term.

### Still TODO

- [ ] **Connect with Penn State IT** — both for a loaner exhibit laptop and for guidance on the safest way to host the engine on Penn State infrastructure instead of Cloudflare.
- [ ] **Get real WWII footage from Dr. Campbell** and load it into `local-media/WWII/assets/` (she committed to sending clips; David to add them to the new folder structure once received — Swiss and any other topics likewise).
- [ ] **Document how the engine works** — the design decisions and structure, for future reference and potential publications (Dr. Campbell explicitly requested this on 2026-07-23; not yet written up beyond this handoff doc and inline code comments).
- [ ] **Research live webcam feed integration** — floated as a future enhancement in the 2026-07-23 meeting; no design work started yet.
- [ ] **Minutes-based duration input** — nice-to-have per Dr. Campbell, not essential; currently seconds-only in the UI.
- [ ] Configure OneDrive Desktop Sync on the eventual exhibit machine.
- [ ] Set Flask to auto-start on boot for that machine.
- [ ] Decide and build the visitor-facing interaction model (staff-started vs. button-triggered).
- [ ] Create a quick-start guide for Dr. Campbell / gallery staff (no Terminal, no code).

### Key dates

- **Museum exhibition: December 2026** — confirmed success date for the project regardless of festival timing.
- **Centre County Film Festival**: Dr. Campbell said the August 8 deadline will likely be missed due to scheduling; a later October call may be a fallback submission target.
- **Internship extension**: David needs to respond to an email about required internship hours; Dr. Campbell confirmed flexibility on hours is fine as long as the project keeps progressing — response pending, possibly CC'ing Dr. Campbell.

## Latest Verified Test

**Test date**: 2026-07-23
**Setup**: Web UI, Validation topic, real browser end-to-end test after the multi-topic migration
**Result**: ✅ PASS

- Topic selector correctly listed all three collections with live clip counts (Validation: 13, WWII: 0, SWISS: 0).
- Selecting an empty topic (WWII) correctly disabled Generate with an explanatory message; no crash.
- Generated a real film from Validation through the actual browser UI — correct collection metadata, title card played correctly at the start, video/audio intact.
- Confirmed (via a scare mid-session, fully recovered) that the 13 clips' hand-authored metadata — moods, weights, tags — survived the migration intact after a background dev-server race briefly corrupted it; recovered from git history and re-verified.

Earlier baseline test (pre-restructure, still representative of core engine behavior): 90s target film played correctly in-browser with full contrast trace and no X-roll-standalone artifacts.

## Architecture Overview

```
Web UI (browser)
    ↓
Flask Backend (app.py)              →  GET /api/collections (list topics)
    ↓                                  POST /api/generate {collection, target_duration, ...}
dde_runtime.py (shared generation logic)
    ↓
list_collections() / get_collection()  →  resolves paths for the selected topic
    ↓
sync_media_library()   →  reconciles that topic's assets/ folder against its metadata index
    ↓
Sequencer (generate)   →  loads collection, builds contrast-ranked sequence
    ↓
Assembler (render)     →  pairs B+X, normalizes media, renders MP4
    ↓
_trim_film_to_duration()    →  (if exact_duration) trims to target minus card time
    ↓
_wrap_with_title_cards()    →  prepends/appends fixed intro + outro cards
    ↓
FFmpeg                 →  H.264 video, AAC stereo, 1280x720, 30fps
    ↓
local-media/<Topic>/artifacts/   →  film_test_1.mp4, film_test_2.mp4, etc.
```

## Important Files

- **Backend**: `web/backend/app.py` — Flask API, multi-collection aware
- **Frontend**: `web/frontend/index.html`, `app.js`, `style.css`, `psu-logo.svg`
- **Shared runtime**: `scripts/dde_runtime.py` — collection registry, sync, trim, title cards, `generate_and_render()`
- **Engine**: `engine/sequencer.py`, `engine/artifact_selector.py`, `engine/rules.py`, `engine/assembler.py` (all collection-path-agnostic — no changes needed for multi-topic support)
- **Metadata**: `metadata/collections/<topic>_collection_index.json` (one per topic; auto-created for new ones)
- **Media**: `local-media/<Topic>/assets/{a-roll,b-roll,x-roll}/`
- **Output**: `local-media/<Topic>/artifacts/` (generated MP4s and manifests, per topic)

## Key Design Decisions

1. **No emotional continuity**: Juxtaposition and contrast drive all sequencing decisions. Mood and pacing metadata are scored dimensions, not enforcement rules.
2. **Diversity mode is optional**: Normal mode keeps a tight top-contrast pool (strongest cuts). Diversity mode widens the pool and boosts underused clips for broader collection exploration.
3. **X-roll paired, never standalone**: Audio-only clips are always paired with B-roll video; they cannot be selected independently.
4. **Whole clips only by default**: The engine never cuts into real footage unless "exact duration" is explicitly enabled — undershooting the target is preferred over trimming a clip.
5. **Fixed cards frame the film, don't compete with it**: The intro/outro cards are a wrapper around the dynamic sequence, not part of the contrast-scored body — they're identical every time on purpose, contrasting with the "different every time" sequence in between.
6. **Topics are self-contained and auto-discovered**: No central registry file to hand-maintain — a topic is just a correctly-shaped folder. This mirrors the existing "drop a file in, the engine adapts" philosophy already established for individual clips.
7. **Local-network architecture**: No cloud dependencies at runtime; media stays on the exhibit machine or OneDrive-synced local storage. (Remote *testing* currently uses a temporary Cloudflare tunnel — not part of the permanent architecture.)

## Conversation & Talking Points

**For Dr. Campbell (non-technical)**:

> "The engine generates a different film every time you click 'Generate.' It picks clips from your media collection and arranges them so consecutive clips contrast as much as possible — different moods, different locations, different subjects. It's designed to surprise and engage viewers, not comfort them. Every film opens and closes on the same title and credit cards, but everything in between is unique each time. You can click as many times as you want."

**For academic/technical audiences**:

- How does the engine differ from traditional documentary editing? (No emotional arc, pure contrast maximization.)
- What happens if the same clips appear in multiple generated films? (Diversity mode prevents oversaturation; usage counts persist across runs.)
- Why B-roll + X-roll pairing? (B-roll is visual-only; X-roll provides layered audio without adding screen time.)
- How does it ensure variety in a small collection? (Dissimilarity scoring + diversity mode + weighted randomness within contrast pool.)
- How does it scale to multiple documentary topics? (Each topic is an independently-scored, independently-stored collection — no cross-topic mixing, but zero code changes needed to add one.)

## Next Steps

1. **Get WWII (and other) footage from Dr. Campbell** and load it into the new per-topic folders.
2. **Follow up with Penn State IT** — a loaner exhibit laptop, and safer hosting than the current Cloudflare tunnel.
3. **Write up how the engine works** for Dr. Campbell's documentation/publication request.
4. **Decide the exhibit interaction model** (staff-started vs. visitor button) and build it.
5. **Test the exhibit setup** on real hardware once IT provides it — local network access, OneDrive sync, auto-start on boot.
6. Lower priority / nice-to-have: minutes-based duration input, live webcam feed research.

## Recommended Test Flow

1. Pick a topic in the web UI (start with Validation, since it has real footage).
2. Generate 5–10 films.
3. Review sequence traces for contrast reasoning.
4. Check that no clip repeats within a film.
5. Verify audio sync and video quality, including the fixed intro/outro cards.
6. Test diversity mode and exact duration together for a few runs.
7. Switch to an empty topic (WWII/SWISS) and confirm Generate is correctly blocked with a clear message.
8. Once real WWII/Swiss footage lands, repeat this whole flow for those topics.

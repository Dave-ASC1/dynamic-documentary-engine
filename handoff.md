# Handoff — Dynamic Documentary Engine

Last updated: 2026-09-28

This is for the student taking the engine over. It assumes you can already
run it (`SETUP-GUIDE.md`) and know what it is (`README.md` — though parts of
the README are stale; `AGENT.md` §7 lists which). This document is the map
and the *why*: how a run flows, why things are built the way they are, where
to make common changes, and what will bite you if nobody warns you.

`AGENT.md` is the short rulebook for anyone (or any tool) editing the code;
read it too. The older, dated session-by-session notes that used to live in
this file are in its git history (`git log -p handoff.md`).

Who to ask: David Ademoye (author) or Dr. Betsy Campbell (supervisor). When a
change touches *what the films are* rather than how the code works — bookend
rules, repeating clips, the look of the title cards — ask before building.

---

## 1. The five-minute mental model

### Vocabulary (locked — use these words exactly)

| Term | Means |
|---|---|
| **Artifact** | One media clip, plus its metadata. |
| **Collection** | A curated set of artifacts for one topic (the web UI calls it a "topic"). |
| **Film** | One generated output. |
| **A-roll** | Video with its own synchronized audio. Stands alone. |
| **B-roll** | Video only. Never stands alone — always paired with an X-roll. |
| **X-roll** | Audio only. Layered under a B-roll. Never shown on its own. |

A **slot** in a film is either one A-roll, or one B-roll + X-roll pair. The
X-roll adds sound, not screen time.

### The modules

| File | Job |
|---|---|
| `engine/collection_loader.py` | Reads a collection index JSON, checks required fields, hands out artifacts. |
| `engine/rules.py` | Yes/no eligibility: no-repeat, duration budget, must-not-follow. Tracks running length. |
| `engine/artifact_selector.py` | Picks the next clip: scores how *different* each candidate is from the last one, then weighted-random picks from the top few. Also picks X-rolls for B-rolls. |
| `engine/sequencer.py` | The coordinator. Builds the ordered sequence: opening pair → body → closing pair. |
| `engine/assembler.py` | Turns the sequence into an MP4 with FFmpeg: one normalized segment per slot, then joins them. |
| `engine/cancellation.py` | Lets the web UI kill a render mid-flight (including the running FFmpeg process). |
| `scripts/dde_runtime.py` | The layer both the CLI and the web backend call. Topic discovery, media auto-sync, the "why this cut" trace, exact-duration trim, title cards, usage stats, manifests. |
| `scripts/run_first_film.py` | Command-line runner. |
| `web/backend/app.py` | Flask API + serves the two frontends. |
| `web/frontend/` | Plain HTML/CSS/JS. `index.html`/`app.js` = researcher console; `exhibit.*` = gallery kiosk. |

The engine package knows nothing about Flask, topics, or title cards. Keep it
that way: engine = sequencing + rendering; `dde_runtime.py` = everything
around it.

### How one run flows

```
Browser (Generate)
  → app.py  POST /api/generate
      → sync_media_library()        reconcile the topic's index with its assets/ folders
      → dde_runtime.generate_and_render()
          → Sequencer.generate()
              1. opening pair   random B-roll + X-roll (weighted by metadata "weight")
              2. closing pair   chosen now and held back; its screen time reserved in the budget
              3. body loop      until the duration budget is used up:
                   selector.select_next()
                     → rules.is_eligible() filter
                     → score every candidate's dissimilarity vs. the previous clip
                     → keep the top 3 (wider in diversity mode)
                     → weighted-random pick among them
                   if it's a B-roll → selector.select_pairing() picks its X-roll
              4. append the closing pair
          → Assembler.render()      one segment per slot at 1280×720 / 30fps, then concat
          → exact-duration trim     (only if that toggle is on)
          → wrap with title cards   opening + closing piece around the whole film
          → write manifest .json    next to the .mp4
```

`Sequencer.generate()` returns a list like
`[("bv_1","xa_2"), "av_4", ("bv_3","xa_1"), "av_2", ("bv_5","xa_2")]` —
strings are A-roll, tuples are B-roll + X-roll. First and last are always
tuples.

---

## 2. Key design decisions, and why

### Juxtaposition, not continuity

The guiding idea is **maximum contrast between neighbouring clips**, not a
smooth emotional arc. `_compute_dissimilarity_score()` in
`artifact_selector.py` adds a point for each way the candidate differs from
the previous clip: media type, mood, pacing, geography, dominant lines, plus
one point for every tag and theme the candidate has that the previous clip
didn't.

Mood and pacing are *scored dimensions*, not rules. There is no pacing arc
(`rules.get_target_pacing()` returns `None`), and the `current_mood` argument
to `select_next()` is accepted but ignored — both are leftovers from an
earlier continuity-based design, kept so the interfaces didn't break.

It picks from the **top 3**, not the single best, on purpose: always taking
the top scorer would make the same cuts every time. The artifact's `weight`
then decides among those three (it's a frequency knob, not a contrast one).
**Diversity mode** widens the pool (60% of candidates, at least 12) and boosts
clips that have appeared less across previous films, using
`usage_stats.json` in the topic's `artifacts/` folder.

### Generated B-roll + X-roll bookends

There is no designated opening or closing clip. Every film opens and closes
on a **random B-roll + X-roll pair from the ordinary pool**. Two details
matter:

- The **closing pair is chosen before the body**, so the body can't use up
  every B-roll and leave the film with no ending.
- Its **screen time is reserved in the budget** up front. Before this, the
  close was tacked on after the budget check and films overshot the target
  by 5–10 seconds.

The bookends are *not* the title cards. Title cards are a fixed wrapper
around the finished film (section on exact duration below); the bookends are
the first and last slots of the dynamic sequence inside it.

Whether A-roll should also be allowed to open/close a film is an **open
design question** — ask David before changing it.

### Audio reuse inside a film

Clips (A-roll and B-roll) never repeat within a film. **X-roll can.** An
audio bed is a layer, not a shot, and each use plays a different random
excerpt of the file. Enforcing no-repeat on audio made the number of audio
files a hard cap on film length (sixteen clips and two recordings could only
make a two-shot film). `select_pairing()` spreads reuse evenly by always
choosing among the least-heard recordings first.

### The concat *filter*, not stream-copy — the audio-bleed fix

Segments are joined with FFmpeg's concat **filter** (decode everything,
re-encode one continuous stream), not the concat demuxer with `-c copy`.

Why: AAC audio comes in 1024-sample frames, and every segment carries its own
padding and priming samples. Stream-copying leaves those in place at every
join, so about **50ms of each clip's audio played over the start of the next
clip** — measured at −24 dBFS (full level) where there should have been
silence. With the filter: −71 dBFS, inaudible.

The cost is speed: rendering is roughly 0.3× the film's length (a 90-second
film takes about 30 seconds). **Don't "optimize" this back to `-c copy`.**

The filter opens every input at once and starts failing past about 200, so
long films are joined in batches of 100 (`CONCAT_BATCH_SIZE`) and the batches
joined in turn. Tested at 900 segments.

### X-roll excerpts instead of looping

When an audio file is shorter than its B-roll, the old approach looped it
(`-stream_loop -1`). The restart was audible — the sound "changed" with no
cut on screen. Now `_plan_xroll_excerpts()` builds the bed from several
excerpts, each from its own random point in the file, joined with a short
(≤0.4s) crossfade. Long audio just gets one excerpt from a random start.
Live streams and unmeasured files still fall back to looping.

### The audio-transition fade

With the fade on, each **B-roll's music bed fades up at the start of the clip
and down at the end**, so every cut dips to silence and back instead of the
music jumping. It's baked into each segment separately.

- **Why a dip, not a crossfade between clips:** overlapping neighbouring
  clips' audio would shift sound against picture, and the drift adds up
  over a full film.
- **Why only B-roll:** A-roll is someone speaking; fading speech in and out
  sounds wrong. A-roll audio is never touched.
- **Why it varies:** the chosen length (dropdown, default 0.8s) is a
  *center*. Each clip's fade-in and fade-out are rolled **independently**
  within ±35% of it, so every cut breathes a little differently and
  re-rendering changes them — in keeping with "no two screenings alike".
- **Guardrails:** a fade is never shorter than 0.15s, and never longer than
  20% of its clip on either side (short clips get short fades; the 20% cap
  wins over the 0.15s floor). "Off" adds no filter at all.

### Exact duration

By default the engine **never cuts into real footage**: it uses whole clips
and lands at or a few seconds under the target. Undershooting is preferred
to chopping a shot.

With **Exact duration** on, the sequencer is allowed to run *past* the
target (`allow_overshoot=True`), then the rendered film is **re-encoded and
trimmed** to exactly the target minus the title cards' length — so the whole
file, cards included, matches what was asked for. The title-card length is
measured from the actual pieces, since a topic's own opener can run minutes.
Re-encoding (not stream-copy) is what makes the cut frame-accurate instead of
snapping to a keyframe. The price: whatever was playing gets cut off
mid-shot. The exhibit view keeps this off.

### Title cards

Every film is wrapped in an opening and closing piece. If
`local-media/<Topic>/titles/opening/` (or `closing/`) contains a video, that's
used, at whatever length. If the folder is empty, a text card is generated
with Pillow (6s opening, 4s closing). Pillow is used instead of FFmpeg's
`drawtext` because many FFmpeg builds don't include it.

### One shared driver, many front doors

The console and the exhibit view both go through
`dde_runtime.generate_and_render()`, so they can't drift apart. Put new
pipeline steps there, not in `app.py`. The CLI (`run_first_film.py`) shares
the tracing, sync and placeholder helpers from `dde_runtime.py` but drives
`Sequencer` and `Assembler` itself, because it also prints a trace and runs
a uniqueness check — so it renders the dynamic sequence only (no title
cards, trim or manifest). If you add an engine option, thread it through
both.

### Topics are just folders

There's no registry. Any `local-media/<Name>/` with `assets/` and
`artifacts/` inside becomes a topic. Its metadata index is treated as a
**cache of what's on disk**, reconciled on every generate.

---

## 3. Where to change common things

### Add a topic

1. Create `local-media/<Name>/assets/a-roll/`, `assets/b-roll/`,
   `assets/x-roll/` and `local-media/<Name>/artifacts/`.
2. Restart the server. It creates
   `metadata/collections/<name>_collection_index.json` (default runtime rules:
   35s min, 1800s max) and the `titles/opening/` + `titles/closing/` folders.
3. Drop clips in. Accepted: A-roll/B-roll `.mov .mp4 .m4v`; X-roll
   `.wav .mp3 .m4a .aac`. On the next generate each new file is added to the
   index with its duration, a pacing guess from its length, a dominant-colour
   tag, and `weight: 0.5`.
4. **Enrich the index by hand.** Auto-tagged clips have almost nothing to
   contrast on, so the scorer can barely tell them apart. Open the topic's
   index and add `mood`, `tags`, `theme`, `geography`, `dominant_lines` and a
   `title` to each entry (see `metadata/collections/validation_collection_index.json`
   for well-tagged examples). This is where most of the engine's quality
   comes from.

A topic needs **at least one B-roll and one X-roll**, or it can't make
bookends and generation fails.

### Adjust the fade

- Constants at the X-roll section of `Assembler` in `engine/assembler.py`:
  `AUDIO_FADE_SECONDS` (default center), `AUDIO_FADE_JITTER`,
  `AUDIO_FADE_MAX_FRACTION`, `AUDIO_FADE_FLOOR_SECONDS`.
- The math: `_fade_center()`, `_fade_seconds()` (per-clip ceiling),
  `_roll_fade()` (one jittered value), `_afade_expr()` (the FFmpeg filter).
  Applied in `_build_broll_xroll_command()`.
- The dropdown options are in `web/frontend/index.html`
  (`#audio-fade-select`); their values are the centers. If a request sends no
  fade setting (the exhibit view, scripts), the backend turns the fade on at
  the default.

### Tune the dissimilarity scoring

- **What counts as different:** `_compute_dissimilarity_score()` in
  `engine/artifact_selector.py`. Every dimension is worth 1 point, except
  tags and themes, which score per unshared value — so clips with lots of tags
  tend to win. To weight a dimension, multiply its contribution.
- **How many top candidates compete:** `_JUXTAPOSITION_POOL_SIZE` (3),
  `_DIVERSITY_POOL_RATIO` (0.6), `_DIVERSITY_POOL_MIN` (12) on
  `ArtifactSelector`.
- **How often a clip is picked:** its `weight` in the index (default 0.5).
- **Keep the trace honest:** `dims()` in `scripts/dde_runtime.py` re-derives
  the same dimensions to explain each cut in the console's "why this cut"
  panel. If you add or reweight a dimension, update `dims()` too.

### Add a metadata field

The important thing to know: **the engine reads the flat per-artifact
entries in the collection index**, not the detailed per-artifact JSON files.
(The assembler reads per-artifact files only to find a live stream's URL.)
So a new field that should affect sequencing needs to:

1. Be added to the entries in `metadata/collections/<topic>_collection_index.json`.
2. Be declared, **optional**, under `artifacts.items.properties` in
   `metadata/collection_index_schema.json` — and under the matching object
   (`content` or `sequencing`) in `metadata/artifact_schema.json` if it
   belongs in the detailed format too.
3. Be read in the scorer or rules using the existing fallback pattern,
   `a.get("x") or a.get("content", {}).get("x")`, so both shapes work.
4. Optionally be inferred for new files in `sync_media_library()`.

Keep new fields optional so existing indexes still load. Note that
`CollectionLoader` only checks for a handful of required fields at load
time; full JSON-schema validation only runs in
`scripts/build_validation_collection.py`.

---

## 4. Gotchas and non-obvious constraints

### Project rules

- **Locked terminology.** A-roll / B-roll / X-roll; artifact / collection /
  film. Don't introduce synonyms in code, UI or docs.
- **No AI model, provider or vendor names anywhere** — code, comments,
  docstrings, filenames, docs. This is a supervisor requirement. The
  assistant/agent context file is `AGENT.md`; don't add a vendor-named one.
  Don't add commit trailers naming a tool or model either.
- **No external generation services.** All sequencing is original
  algorithmic code. No API calls out to anything for generation.
- The engine's inspiration and comparison with other generative film work
  lives in `docs/` only — keep it out of code.
- **Branch flow:** work on `first-run-demo`, get it verified, then promote to
  `main` by fast-forward. Never push straight to `main`. The repo is public.
- Keep the author/credit header at the top of every Python file.

### Media and generated files

- **Media isn't in git.** A fresh clone has empty `assets/` folders; the
  footage travels separately (drive, OneDrive, copied on the day).
- **Media is ignored by folder.** `local-media/.gitignore` ignores everything
  inside each topic's `assets/`, `titles/` and `artifacts/` folders, whatever
  the file type, except the `.gitkeep` placeholders and title READMEs. Those
  placeholders matter: a topic is only discovered if its `assets/` and
  `artifacts/` folders exist, so don't delete them. Media dropped anywhere
  *else* is only caught by the root `.gitignore`'s `*.mp4 *.mov *.wav *.mp3`.
- **Generated films, their `.json` manifests and `usage_stats.json` are
  gitignored.** They land in `local-media/<Topic>/artifacts/`. Leave them out
  of commits. Delete `usage_stats.json` to reset diversity mode's history.
- **Renaming or deleting a media file throws away its hand-written
  metadata.** The sync matches files by name: a missing file's entry is
  removed, and a renamed file comes back as a new, bare auto-tagged entry.
  Rename in the index too, or re-enter the metadata.

### Behaviour that surprises people

- **Footage is the ceiling on length.** Clips never repeat, so a film can't
  be longer than the topic's total A-roll + B-roll footage. Ask for 90
  minutes from 2 minutes of footage and you get about 2 minutes — not an
  error. Allowing repeats would be a design decision, not a bug fix.
- **The CLI isn't the web app.** `scripts/run_first_film.py` defaults to
  `demo/` with generated placeholder media and the Validation index. Use
  `--topic <id>` (e.g. `--topic wwii`) for a topic's real footage; it then
  writes into that topic's `artifacts/` folder like the web app does. The
  fade is on at 0.8s by default (`--fade 0` for hard cuts). There are no
  title cards or trim in CLI films.
- **Never sync a folder into another topic's index.** Syncing retires every
  entry whose file isn't in the folder, hand-written metadata included. The
  CLI refuses to do this, but anything new that calls `sync_media_library()`
  must pair each topic's `assets/` with its own index.
- **`must_not_follow` compares against the last shot on screen** (the last
  A-roll or B-roll), not the audio under it. The closing pair is chosen
  before the body exists, so it can't honour the rule against the clip
  before it.
- **Title-card fonts:** Georgia and Arial, found in the macOS or Windows font
  folders (DejaVu on Linux). If none is found, the cards render in Pillow's
  plain built-in font.
- **Port 5001, not 5000** — macOS AirPlay Receiver takes 5000. Set `PORT` to
  override; the server also moves to the next free port on its own.
  `DDE_DEBUG=1` turns on Flask debug; `DDE_NO_BROWSER=1` stops it opening a
  browser tab.
- **There's no test suite.** Verify with `scripts/run_first_film.py`, the
  console, `ffprobe`, and your ears. For audio changes, listen at the cuts.
- **Known schema bug:** some nullable example fields in
  `metadata/artifact_schema.json` are typed as plain `string`/`number` but set
  to `null` (details in `AGENT.md` §4). Confirm the fix direction with David.

---

## 5. Open threads and future directions

None of these have been started unless it says otherwise.

- **Loudness normalization — not started.** Clips come in at very different
  volumes. FFmpeg's `loudnorm` per segment (in `assembler.py`) would even them
  out. It's a separate change from the fade and shouldn't be mixed into it.
  Two-pass `loudnorm` is more accurate but doubles audio analysis time.
- **Context-aware "memory triggers" — not started.** Dr. Campbell's idea: let
  real-world context (date, weather, and so on) influence what the engine
  picks. A research direction for a future version, well beyond the current
  local system.
- **A-roll as bookends — undecided.** Should A-roll be allowed to open or
  close a film? Currently only B-roll + X-roll can. Needs David / Dr. Campbell.
- **Live webcam / stream input — not started beyond the plumbing.** The
  assembler can read a `stream` source type from a per-artifact JSON file,
  but there's no UI or workflow for adding one.
- **README refresh — not started.** It still describes the old approach. See
  `AGENT.md` §7.
- **A proper test suite — not started.** The most valuable first tests would
  pin down the sequencer's guarantees: bookends are always B-roll + X-roll,
  no clip repeats, the budget is respected.
- **Exhibit deployment — status last recorded 2026-08-17; check with Dr.
  Campbell.** Open at that point: a Penn State IT loaner laptop and hosting
  (instead of a temporary tunnel), real WWII and Swiss footage, syncing
  footage to the exhibit machine, and starting the server on boot. The target
  was a museum exhibition in December 2026.

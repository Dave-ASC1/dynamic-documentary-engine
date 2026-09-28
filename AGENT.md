# AGENT.md — Dynamic Documentary Engine (DDE)

> Operating brief for AI coding assistants / agents working on this repository.
> Read this document before making changes.
> Where this file and the code disagree, **trust the code** and flag the discrepancy to David.
> Note: the repo `README.md` is partly **stale** (see §7) — do not treat it as authoritative. `SETUP-GUIDE.md` (how to install and run) and `handoff.md` are the other living docs.

---

## 0. First run — do this before writing code

1. Read the engine in full: `engine/sequencer.py`, `engine/collection_loader.py`, `engine/rules.py`, `engine/artifact_selector.py`, `engine/assembler.py`, `engine/cancellation.py`, `engine/__init__.py`.
2. Read `scripts/dde_runtime.py` (the shared engine-driving layer used by both the CLI and the web backend) and `web/backend/app.py`.
3. Read `metadata/artifact_schema.json` and `metadata/collection_index_schema.json`.
4. Confirm §4 (current state) still matches the code. If it drifted, tell David before proceeding.
5. Confirm the branch flow (§10) before committing: work lands on `first-run-demo` first, then is promoted to `main`.

---

## 0a. Continuity / handoff note

David (Oluwafemisola David Ademoye) built this engine essentially solo for an IST 495 research internship, and has since graduated. The project is transitioning toward new incoming students who will carry it forward. If you are one of them: start at `SETUP-GUIDE.md` to get it running, then read this file and the engine (§0). Preserve the author/credit headers in each file. When in doubt about direction, ask David or Dr. Betsy Campbell rather than guessing.

---

## 1. What this project is

The **Dynamic Documentary Engine (DDE)** is a generative film engine. On every run it assembles a **unique** film from modular media artifacts — no two screenings are the same.

Guiding philosophy: **maximum juxtaposition, not emotional continuity.** Every cut should maximize dissimilarity between adjacent clips rather than smooth an emotional arc. Conceptually analogous to Brian Eno's *Brain One* engine (Brendan Dawes, 2024 *Eno* documentary), but **original and open-source**.

---

## 2. Non-negotiable rules

1. **No specific AI model, provider, or vendor names in the codebase** — comments, docstrings, schema fields, variable names, filenames. (Explicit supervisor requirement. The repo is clean of these — keep it that way.) This extends to repo docs and filenames: the agent/context file is named **`AGENT.md`** — do not create a vendor- or model-named equivalent.
2. **No external AI or generation services.** All sequencing is **original algorithmic "creative code."** No API calls to any AI engine for generation.
3. **B-roll never stands alone** — always paired with an X-roll to supply audio.
4. **Every film opens and closes** with an automatically generated bookend — a randomized **B-roll + X-roll pair** drawn from the body pool (the closing pair is reserved before body selection so the film always has an ending). If A-roll should also be eligible to bookend, that is a deliberate design change — confirm with David first.
5. The **Brian Eno / *Brain One*** framing lives only in `docs/` and the research report — keep it out of code.
6. **Preserve the locked terminology** (§3) exactly.

---

## 3. Terminology (locked)

- **Artifact** — an individual media clip.
- **Collection** — a full curated set of artifacts (also called a "topic" in the web layer). Films open and close with generated B-roll+X-roll bookends drawn from the body pool (rule 4); there is no designated opening/closing A-roll.
- **Film** — a generated output.
- **A-roll** — synchronized audio + video; stands alone.
- **B-roll** — video only; must always be paired with X-roll.
- **X-roll** — audio only; layered over B-roll.

Collection class hierarchy: `CL-AV` (A-roll), `CL-V` (B-roll), `CL-A` (X-roll).

---

## 4. Current state (verify on first run)

Engine package version **2.0.0**. The juxtaposition rewrite is implemented, and the pipeline, a Flask backend, and a browser UI (console + exhibit view) are all working end to end on real media.

**Real file tree (excluding `.git`, `__pycache__`, and gitignored media):**
```
dynamic-documentary-engine/
├── engine/
│   ├── __init__.py            # exports the public API (see §8)
│   ├── sequencer.py           # Sequencer — top-level coordinator; generates bookends + body
│   ├── collection_loader.py   # CollectionLoader — loads/validates a collection index
│   ├── rules.py               # SequencingRules — eligibility, no-repeat, duration budget
│   ├── artifact_selector.py   # ArtifactSelector — dissimilarity scoring + juxtaposition
│   ├── assembler.py           # Assembler — FFmpeg pipeline (lives here, NOT in pipeline/)
│   └── cancellation.py        # CancellationToken — cooperative cancel for in-flight renders
├── metadata/
│   ├── artifact_schema.json               # per-artifact schema (Draft-07, allOf validation)
│   ├── collection_index_schema.json       # schema for a full collection index
│   ├── ww2_av_003_example.json            # legacy example A-roll artifact
│   ├── ww2_bv_live_001_example.json       # legacy example B-roll (live-stream) artifact
│   ├── collections/                       # per-topic collection indexes
│   │   ├── wwii_collection_index.json
│   │   ├── swiss_collection_index.json
│   │   └── validation_collection_index.json
│   └── validation/                        # the validation collection's per-artifact JSON
├── scripts/
│   ├── build_validation_collection.py     # generator for the ORIGINAL placeholder set (guarded)
│   ├── dde_runtime.py                      # shared engine-driving helpers (CLI + backend)
│   └── run_first_film.py                   # end-to-end CLI: generate → render + trace
├── web/
│   ├── backend/app.py                      # Flask API (see below)
│   └── frontend/
│       ├── index.html style.css app.js     # researcher console (single page)
│       ├── exhibit.html exhibit.css exhibit.js  # kiosk / gallery view
│       └── psu-logo.svg
├── local-media/                            # real footage workspace (media gitignored)
│   ├── WWII/  SWISS/  Validation/          # one folder per topic: assets/ + artifacts/ + titles/{opening,closing}/
│   └── README.md                           # web-generated films + .json manifests land in <Topic>/artifacts/ (gitignored)
├── demo/                                   # gitignored; CLI default output + placeholder media
├── docs/  (comparative_analysis_brain_one.md, sketches/*.jpg)
├── Start Engine (Mac).command              # double-click launchers for the web UI
├── Start Engine (Windows).bat
├── requirements.txt
├── SETUP-GUIDE.md   # beginner install/run guide (Windows + Mac)
├── handoff.md       # handoff notes
├── AGENT.md         # this file
├── README.md        # PARTLY STALE — see §7
└── LICENSE          # MIT
```

**Sequencing (engine/):**
- `sequencer.py` — opens AND closes each film with a **generated randomized B-roll+X-roll pair** from the body pool (closing pair reserved before body selection). `generate(target_duration, allow_overshoot=False)` reserves the closing clip's screen time in the budget so whole clips don't overshoot the target. Body picks come from any eligible A-roll or B-roll; X-roll is only ever a B-roll's audio partner, never standalone.
- `rules.py` — no forced A/B pacing arc (`get_target_pacing()` returns `None`). Enforces no-repeat, duration budget, must-not-follow. X-roll pairing skips the duration budget (it adds no screen time).
- `artifact_selector.py` — dissimilarity scoring ranks the **most unlike** next artifact across type, mood, pacing, tags, theme, geography, dominant lines. Normal mode = tight top-3 weighted-random pool; **diversity mode** widens the pool by collection size and boosts underused artifacts via persisted usage counts.

**Rendering (engine/assembler.py):**
- Class-based FFmpeg pipeline; mixed sequences, local-file and live-stream sources; normalizes every segment to a common geometry (default **1280×720, 30fps**, libx264/aac) so mixed-resolution / portrait / 4K footage concatenates cleanly.
- **Concat uses the concat *filter* (decode + re-encode), NOT the stream-copy demuxer.** This fixed an audio "bleed" where ~50ms of each clip's audio carried over the next cut (measured −24 dBFS with the demuxer vs −71 dBFS, inaudible, now). Long films are joined in batches (`CONCAT_BATCH_SIZE = 100`) and the batches joined recursively.
- **X-roll under B-roll** is assembled from an excerpt plan (`_plan_xroll_excerpts`), not plain looping: a random start offset each render, and if the audio is shorter than the clip it chains several random excerpts with short internal `acrossfade`s (replaces the audible `-stream_loop` restart). Live/unmeasured sources fall back to `-stream_loop -1`.
- **Optional audio-transition fade** (per run): fades each B-roll music bed **up at the clip's start and down at its end** (a dip to silence and back across each cut), so the soundtrack doesn't jump. A-roll speech is left crisp. The chosen length (default `AUDIO_FADE_SECONDS = 0.8`) is the **center**: each clip's fade-in and fade-out are rolled **independently** within ±35% of it (`AUDIO_FADE_JITTER`), so every cut breathes differently and re-rendering varies them. Each fade is clamped to at least `AUDIO_FADE_FLOOR_SECONDS = 0.15` and at most **20% of the clip per side** (`AUDIO_FADE_MAX_FRACTION`; the cap wins on very short clips). Off is a true no-op (no filter). Controlled per run by `audio_fade` / `audio_fade_seconds` (see §8) and, in the UI, the "Audio transitions" dropdown.

**Web layer (web/backend/app.py + scripts/dde_runtime.py):**
- Auto-discovers every topic folder under `local-media/` (currently WWII, SWISS, Validation) — no hardcoded media path.
- **Media auto-sync:** drop clips into `local-media/<Topic>/assets/{a-roll,b-roll,x-roll}/` and they're detected on the next request without regenerating anything.
- Endpoints: `GET /` (console), `GET /exhibit` (kiosk), `GET /<path>` (frontend static files), `GET /api/collections`, `POST /api/generate` (accepts `collection`, `target_duration`, `diversity_mode`, `exact_duration`, `audio_fade`, `audio_fade_seconds`, `job_id`), `POST /api/generate/cancel`, `GET /api/generate/progress?job_id=`, `GET /api/films?collection=` (history), `DELETE /api/films/<collection>/<file>`, `GET /films/<collection>/<file>`.
- **Cancel:** the client makes a `job_id`, sends it with generate, and can POST it to cancel — the running FFmpeg process is killed via the `CancellationToken`.
- **Exact duration:** trims the final file to exactly `target_duration` (minus title-card length). Title cards wrap every film's open/close.
- Each film writes a **manifest** (`.json` beside the `.mp4`) recording `generated_at`, target/actual duration, and the slot list.

**Frontend:**
- **Console** (`index.html`/`app.js`): topic picker, target length (seconds/minutes), Diversity + Exact-duration toggles, **Audio transitions dropdown** (Off / Subtle 0.3 / Balanced 0.5 / Smooth 0.8 / Long 1.2s; default **Smooth**), Generate/Cancel, a "why this cut" dissimilarity trace, film history (shows **date + time**, per-film delete), light/dark theme.
- **Exhibit** (`exhibit.html`/`exhibit.js`): single-button kiosk view with progress and pause, for public/gallery use.

**Validation state:**
- A live validation collection is wired to real footage; the full pipeline (`scripts/run_first_film.py`) renders a valid H.264/AAC MP4 and all metadata validates against both schemas.
- Still **no `tests/` directory** — validation is via the script, not a unit-test suite.
- `collection_index_schema.json` no longer requires `opening_artifact_id` / `closing_artifact_id` (bookends are generated); those remain optional/deprecated.

**Known pre-existing bug (not from recent edits):** in `artifact_schema.json`, some nullable example fields (`file.stream_url`, `file.filename`, `ai_enrichment.enrichment_date`, `ai_enrichment.confidence_score`) are typed as plain `string`/`number` but set to `null` in examples. Either widen the types to `["string","null"]` / `["number","null"]` or drop the keys when unused. Confirm direction with David before changing.

---

## 5. Build sequence (status)

1. ✅ Diverse, cross-category validation collection + index (`metadata/validation/`, wired to real media).
2. ✅ End-to-end CLI (`scripts/run_first_film.py`): collection → `Sequencer.generate()` → `Assembler.render()` → film, printing the chosen sequence and why each pick was most dissimilar.
3. ✅ Flask backend (`web/backend/app.py`).
4. ✅ Browser UI — a working **plain HTML/CSS/JS** console plus a separate exhibit/kiosk view. (React was the *original* plan; the vanilla UI is what shipped and is deliberately swappable without touching the engine or backend API. Moving to React would be a deliberate change — confirm scope with David.)
5. ⏳ Technical documentation report (where the Brian Eno / *Brain One* framing is used).

> **Data note:** validation data is intentionally **cross-category** (war, nature, archival, modern, somber, absurd) — NOT single-theme — to give the dissimilarity scoring more contrast. The `ww2_*` names are legacy, not a mandate to stay WW2-only.

---

## 6. Current focus / open items

The engine, pipeline, backend, and UI are complete and validated end to end on real media. Current work is polish + handoff, not new architecture:

1. **Handoff / documentation** for the incoming students (this file, `SETUP-GUIDE.md`, `handoff.md`) — the priority as David transitions off.
2. **Audio:** the transition fade is done. Possible next lever — **loudness normalization** (FFmpeg `loudnorm`) so clips sit at an even level (a separate change from the fade). Not built.
3. **Context-aware "memory triggers"** (Dr. Campbell's idea: react to real-world context like date/weather) — a research direction for a *future* version, well beyond the current local system. Not built.
4. **Open design question (needs David):** should A-roll be eligible to open/close a film? (rule 4). Currently bookends are B-roll+X-roll only.

Optional adjacent cleanup, only with David's OK: the nullable-field schema bug (§4); refreshing the stale `README.md` (§7). (Generated film manifests and usage stats are now gitignored.)

Confirm with David before major new stages.

---

## 7. README status

`README.md` is partly stale and must not be treated as ground truth:
- Its "Project Structure" lists `pipeline/`, `films/`, `assets/` and puts the assembler in `pipeline/` — none of that matches the real tree (assembler is in `engine/`).
- It still describes the **old** approach ("pacing arc", "AI as director", "AI-powered", "emotional transitions"). The code is juxtaposition/creative-code with no external AI.
- Updating it to match the current design is reasonable — confirm scope with David first.

---

## 8. Public API (from `engine/__init__.py`, verify signatures in code)

```python
from engine import Sequencer, Assembler, CollectionLoader, SequencingRules, ArtifactSelector

sequencer = Sequencer(collection_path)                 # e.g. "metadata/collections/wwii_collection_index.json"
sequence  = sequencer.generate(target_duration=600)    # seconds, 1–9999; allow_overshoot=False by default
# also: sequencer.generate_multiple(count, target_duration=None)

assembler = Assembler(
    loader=sequencer.loader,
    assets_path="/Volumes/<drive>/dde-assets/",
    films_path="/Volumes/<drive>/dde-films/",
    audio_fade=False,              # enable the transition fade
    audio_fade_seconds=None,       # center fade length (jittered ±35%); None = AUDIO_FADE_SECONDS (0.8)
)
film_path = assembler.render(sequence)                 # returns output MP4 path
```

- `Sequencer.generate()` returns a mixed sequence: strings for A-roll IDs, tuples for B-roll/X-roll pairs. First and last entries are generated bookend tuples (rule 4).
- `CollectionLoader`: `get_artifacts()`, `get_body_artifacts()`, `get_runtime_rules()`.
- `SequencingRules`: `is_eligible()`, `is_eligible_for_pairing()`, `get_target_pacing()`, `register_selection()`, `register_pairing_selection()`, `has_reached_minimum_duration()`, `has_reached_maximum_duration()`, `reset()`.
- `ArtifactSelector`: `select_next()`, `select_pairing()`, `set_previous_artifact()`, `weighted_random_choice()`.
- `engine/cancellation.py`: `CancellationToken` (`cancel()`, `raise_if_cancelled()`) + `GenerationCancelled`.
- Most end-to-end driving (tracing, placeholder media, render, exact-duration trim, title cards, manifests) lives in `scripts/dde_runtime.py` — chiefly `generate_and_render(...)`, which the CLI and the Flask backend both call so they never drift. It threads `diversity_mode`, `exact_duration`, `audio_fade`, `audio_fade_seconds`, `cancel_token`, and a `progress_callback` down to the engine.

---

## 9. Code conventions

- **Python** core; **FFmpeg** rendering; **Flask** backend; plain **HTML/CSS/JS** frontend (React only if deliberately adopted).
- Every Python file uses **Google-style docstrings** with a file header: Author, Supporting, Project, Institution, Supervisor, Version.
- Author: **Oluwafemisola David Ademoye**; Supporting: **Omotola Ajibike Ajao**; Supervisor: **Dr. Betsy Campbell**; Institution: **Penn State, College of IST**.
- Schema: JSON, Draft-07, `allOf` conditional validation.
- Keep generation logic original and dependency-light (`requirements.txt`: flask, jsonschema).
- Media assets live on an **external hard drive** (physical, not cloud) via a **configurable base path** in the Assembler.
- Tuning constants are class attributes on `Assembler` (output geometry/codecs near the top of the class; `AUDIO_FADE_SECONDS`, `AUDIO_FADE_JITTER`, `AUDIO_FADE_MAX_FRACTION`, `AUDIO_FADE_FLOOR_SECONDS`, excerpt settings beside the X-roll code; `CONCAT_BATCH_SIZE` beside the concat code). Selector pool sizes are class attributes on `ArtifactSelector`.
- Commits carry no AI co-author or vendor trailers.

---

## 10. Project facts

- **Course:** IST 495 research internship — **complete**; David has **graduated** (Aug 2026). Check-ins with Dr. Campbell are biweekly and winding down as the project transitions to new students.
- **Repos:** `Dave-ASC1/dynamic-documentary-engine` (primary, **public**, shared with Dr. Campbell); `Dave-ASC1/doc-engine-clone` (experimental, private, David only).
- **Branch flow:** work goes to **`first-run-demo`** (staging) first, is verified, then promoted to **`main`** (default/stable) via fast-forward merge.
- **Git workflow:** David commits and pushes from his own Mac Terminal (HTTPS auth via his credentials / a PAT with `repo` scope). Reads (clone/fetch) work anonymously since the repo is public.

---

## 11. Working with David

- Prefer **conversational, human-sounding explanations** over bullet dumps.
- When work is done, give a plain-language summary he can reuse in Dr. Campbell check-ins.
- Surface any discrepancy between this brief and the real code rather than silently working around it.

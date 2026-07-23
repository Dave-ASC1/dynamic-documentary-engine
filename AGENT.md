# AGENT.md — Dynamic Documentary Engine (DDE)

> Operating brief for AI coding assistants working on this repository.
> Read this document before making changes.
> Where this file and the code disagree, **trust the code** and flag the discrepancy to David.
> Note: the repo `README.md` is partly **stale** (see §7) — and should not be treated as the authoritative source.

---

## 0. First run — do this before writing code

1. Read the engine in full: `engine/sequencer.py`, `engine/collection_loader.py`, `engine/rules.py`, `engine/artifact_selector.py`, `engine/assembler.py`, `engine/__init__.py`.
2. Read `metadata/artifact_schema.json` and `metadata/collection_index_schema.json`.
3. Confirm §4 (current state) still matches the code. If it drifted, tell David before proceeding.
4. Start on the **Immediate next task** (§6). Do not jump ahead to backend/frontend.

---

## 1. What this project is

The **Dynamic Documentary Engine (DDE)** is a generative film engine. On every run it assembles a **unique** film from modular media artifacts — no two screenings are the same.

Guiding philosophy: **maximum juxtaposition, not emotional continuity.** Every cut should maximize dissimilarity between adjacent clips rather than smooth an emotional arc. Conceptually analogous to Brian Eno's *Brain One* engine (Brendan Dawes, 2024 *Eno* documentary), but **original and open-source**.

---

## 2. Non-negotiable rules

1. **Do not introduce references to any specific AI model, provider, or vendor in the codebase unless explicitly required by the project.** — comments, docstrings, schema fields, variable names, filenames. (Explicit supervisor requirement. The repo is currently clean of these — keep it that way.)
2. **No external AI or generation services.** All sequencing is **original algorithmic "creative code."** No API calls to any AI engine for generation.
3. **B-roll never stands alone** — always paired with an X-roll to supply audio.
4. **Every film opens and closes** with an automatically generated bookend. The current engine generates each opening and closing as a randomized **B-roll + X-roll pair** drawn from the body pool (the closing pair is reserved before body selection so the film always has an ending). Earlier designs used a fixed designated opening/closing A-roll; that is no longer how the code works. (If A-roll should also be eligible to bookend a film, that is a deliberate design change — confirm with David before making it.)
5. The **Brian Eno / *Brain One*** framing lives only in `docs/` and the research report — keep it out of code.
6. **Do not build the frontend before the pipeline is validated end-to-end** (§5).
7. **Preserve the locked terminology** (§3) exactly.

---

## 3. Terminology (locked)

- **Artifact** — an individual media clip.
- **Collection** — a full curated set of artifacts. Films open and close with generated B-roll+X-roll bookends drawn from the body pool (see rule 4); there is no longer a designated opening/closing A-roll.
- **Film** — a generated output.
- **A-roll** — synchronized audio + video; stands alone.
- **B-roll** — video only; must always be paired with X-roll.
- **X-roll** — audio only; layered over B-roll.

Collection class hierarchy: `CL-AV` (A-roll), `CL-V` (B-roll), `CL-A` (X-roll).

---

## 4. Current state (verify on first run)

Engine package version **2.0.0**. The juxtaposition rewrite is implemented in code.

**Real file tree (excluding `.git`, `__pycache__`, and gitignored media):**
```
dynamic-documentary-engine/
├── engine/
│   ├── __init__.py            # exports the public API (see §8)
│   ├── sequencer.py           # Sequencer — top-level coordinator; generates bookends + body
│   ├── collection_loader.py   # CollectionLoader — loads/validates a collection index
│   ├── rules.py               # SequencingRules — eligibility, no-repeat, duration budget
│   ├── artifact_selector.py   # ArtifactSelector — dissimilarity scoring + juxtaposition
│   └── assembler.py           # Assembler — FFmpeg pipeline (lives here, NOT in pipeline/)
├── metadata/
│   ├── artifact_schema.json               # per-artifact schema (Draft-07, allOf validation)
│   ├── collection_index_schema.json       # schema for a full collection index
│   ├── ww2_av_003_example.json            # legacy example A-roll artifact
│   ├── ww2_bv_live_001_example.json       # legacy example B-roll (live-stream) artifact
│   └── validation/                        # the live validation collection (14 artifacts)
│       ├── val_*.json                     # 6 A-roll, 4 B-roll, 4 X-roll (wired to real media)
│       └── validation_collection_index.json
├── scripts/
│   ├── build_validation_collection.py     # generator for the ORIGINAL placeholder set (guarded)
│   ├── dde_runtime.py                      # shared engine-driving helpers (CLI + backend)
│   └── run_first_film.py                   # end-to-end CLI: generate → render + trace
├── web/
│   ├── backend/app.py                      # Flask API (generate / list films / serve film)
│   └── frontend/                           # single-page UI: index.html, style.css, app.js
├── local-media/                            # real footage workspace (media gitignored)
│   ├── assets/{a-roll,b-roll,x-roll}/      # engine-ready real clips
│   ├── raw/  films/                        # source downloads / rendered local films
│   └── README.md  .gitignore
├── demo/                                    # gitignored placeholder assets + rendered demo films
├── docs/  (comparative_analysis_brain_one.md, sketches/*.jpg)
├── requirements.txt   # flask, jsonschema
├── README.md   # PARTLY STALE — see §7
└── LICENSE     # MIT
```

**Key behaviors already in code:**
- `sequencer.py` — opens AND closes each film with a **generated randomized B-roll+X-roll pair** from the body pool (closing pair reserved before body selection). Body picks come from any eligible A-roll or B-roll; X-roll is only ever used as a B-roll's audio partner, never standalone.
- `rules.py` — `PACING_ARC`/`position_ratio` removed; `get_target_pacing()` now returns `None` (no A-roll/B-roll alternation is forced). Enforces no-repeat, duration budget, must-not-follow. `is_eligible_for_pairing()` / `register_pairing_selection()` skip the duration budget for X-roll audio (it plays under the B-roll, adding no screen time).
- `artifact_selector.py` — `_compute_dissimilarity_score()` + `_apply_juxtaposition_filter()` rank the **most unlike** next artifacts across type, mood, pacing, tags, theme, geography, dominant lines. Normal mode uses a tight top-3 weighted-random pool; diversity mode widens the pool proportionally to collection size and boosts underused artifacts using persisted usage counts. `select_pairing()` scores the X-roll against the B-roll it accompanies; `weighted_random_choice()` picks bookend candidates without registering them.
- `assembler.py` — class-based FFmpeg pipeline; handles mixed sequences, local-file and live-stream sources, layers X-roll over B-roll (`-stream_loop -1`, `-shortest`), **normalizes every segment to a common geometry** (default 1280×720, 30fps) so mixed-resolution/portrait/4K real footage concatenates cleanly, then stream-copies the concat. Writes uniquely-named MP4s.
- `artifact_schema.json` — `file` object carries `source_type` ("local" | "stream") and `stream_url`; `allOf` conditional validation enforces per-type required fields.

**Current validation state:**
- A live 14-artifact validation collection exists at `metadata/validation/`, wired to real footage in `local-media/assets/`. The full pipeline has been run end to end (`scripts/run_first_film.py`) and renders a valid H.264/AAC MP4 from the real media; all metadata validates against both schemas.
- Still **no `tests/` directory** — validation is via the `run_first_film.py` script, not a unit-test suite.
- `collection_index_schema.json` no longer requires `opening_artifact_id` / `closing_artifact_id` (bookends are generated); those fields remain optional/deprecated for backward compatibility.

**Known pre-existing bug (not from recent edits):** in `artifact_schema.json`, nullable example fields (`file.stream_url`, `file.filename`, `ai_enrichment.enrichment_date`, `ai_enrichment.confidence_score`) are typed as plain `string`/`number`, but the example artifacts set them to `null`. Either the types should be `["string", "null"]` / `["number", "null"]`, or the examples shouldn't include those keys when unused. Confirm intended direction with David before changing.

---

## 5. Build sequence (in order)

1. ✅ Build a **diverse, multi-category** validation collection (10–20 artifacts) + its collection-index JSON. *(Done — `metadata/validation/`, wired to real media.)*
2. ✅ Write an **end-to-end test script**: collection → `Sequencer.generate()` → `Assembler.render()` → film, printing the chosen sequence and why each pick was most dissimilar. *(Done — `scripts/run_first_film.py`.)*
3. ✅ Flask backend. *(Done — `web/backend/app.py`, minimal.)*
4. ⏳ React frontend. *(In progress: currently a plain HTML/CSS/JS single page in `web/frontend/` as a fast, swappable placeholder — NOT React yet.)*
5. Technical documentation report (where the Brian Eno / *Brain One* framing is used).

Never build a later stage before the earlier ones are validated.

> **Data note:** validation data is intentionally **cross-category** (e.g. war, nature, archival, modern, somber, absurd) — NOT single-theme. Wide variety gives the dissimilarity scoring more contrast and is a stronger test of the juxtaposition logic. (The `ww2_*` example files are legacy naming, not a mandate to stay WW2-only.)

---

## 6. Immediate next task

Stages 1–3 of §5 are complete and the pipeline is validated end to end on real media. Current focus / open items:

1. **Frontend polish / real UI.** `web/frontend/` is a working plain HTML/JS placeholder (Generate button, video player, "why this cut" trace, film history). Upgrade toward the real exhibit UI (React was the original plan) — but confirm scope with David; the placeholder is deliberately swappable without touching the engine or backend API.
2. **Turnkey / exhibit packaging.** The end goal is a zero-technical-touch experience (local + web) an art-exhibit visitor or Dr. Campbell can run without code. Not built yet.
3. **Open design question (needs David):** bookends are currently generated B-roll+X-roll pairs; A-roll is not eligible to open/close. Decide whether A-roll should also be eligible (see rule 4).

Optional adjacent cleanup, only if David approves: fix the nullable-field schema bug noted in §4; sync `scripts/build_validation_collection.py` SPECS to the real media (currently guarded against overwriting).

Confirm with David before major new stages.

---

## 7. README status

`README.md` is partly stale and must not be treated as ground truth:
- Its "Project Structure" lists `pipeline/`, `web/`, `films/`, `assets/` and puts the assembler in `pipeline/` — none of that reflects the real tree (assembler is in `engine/`).
- It still describes the **old** approach ("pacing arc, mood transition logic", "AI as director", "AI-powered", "emotional transitions"). The code has moved to juxtaposition/creative-code with no external AI.
- Updating the README to match the current design is a reasonable task — but confirm scope with David first.

---

## 8. Public API (from `engine/__init__.py`, verify signatures in code)

```python
from engine import Sequencer, Assembler, CollectionLoader, SequencingRules, ArtifactSelector

sequencer = Sequencer(collection_path)                 # e.g. "metadata/<collection>_index.json"
sequence  = sequencer.generate(target_duration=600)    # target_duration in seconds, 1–9999
# also: sequencer.generate_multiple(count, target_duration=None)

assembler = Assembler(
    loader=sequencer.loader,
    assets_path="/Volumes/<drive>/dde-assets/",
    films_path="/Volumes/<drive>/dde-films/",
)
film_path = assembler.render(sequence)                 # returns output MP4 path
```

- `Sequencer.generate()` returns a mixed sequence: strings for A-roll IDs, tuples for B-roll/X-roll pairs. The first and last entries are generated B-roll/X-roll bookend tuples (see rule 4).
- `CollectionLoader` exposes `get_artifacts()`, `get_body_artifacts()`, `get_runtime_rules()`. (The old `get_opening_artifact_id()` / `get_closing_artifact_id()` were removed when bookends became generated — opening/closing are no longer fixed IDs.)
- `SequencingRules`: `is_eligible()`, `is_eligible_for_pairing()`, `get_target_pacing()`, `register_selection()`, `register_pairing_selection()`, `has_reached_minimum_duration()`, `has_reached_maximum_duration()`, `reset()`.
- `ArtifactSelector`: `select_next()`, `select_pairing()`, `set_previous_artifact()`, `weighted_random_choice()`.
- Shared runtime helpers for driving the engine end to end (used by both the CLI script and the Flask backend) live in `scripts/dde_runtime.py` — `generate_and_render()`, plus read-only selection tracing and placeholder-media generation.

---

## 9. Code conventions

- **Python** core; **FFmpeg** rendering; **Flask** (planned) backend; **React** (planned) frontend.
- Every Python file uses **Google-style docstrings** with a file header: Author, Supporting, Project, Institution, Supervisor, Version.
- Author: **Oluwafemisola David Ademoye**; Supporting: **Omotola Ajibike Ajao**; Supervisor: **Dr. Betsy Campbell**; Institution: **Penn State, College of IST**.
- Schema: JSON, Draft-07, `allOf` conditional validation.
- Keep generation logic original and dependency-light.
- Media assets live on an **external hard drive** (physical, not cloud) via a **configurable base path** in the Assembler.

---

## 10. Project facts

- **Course:** IST 495 research internship. **Deadline:** August 8th. **Check-ins:** biweekly with Dr. Campbell.
- **Repos:** `Dave-ASC1/dynamic-documentary-engine` (primary, shared with Dr. Campbell); `Dave-ASC1/doc-engine-clone` / `doc-e-c` (experimental clone, David only).
- **Git workflow:** David commits and pushes from his own Terminal (Mac). HTTPS auth via a Personal Access Token with `repo` scope.

---

## 11. Working with David

- Prefer **conversational, human-sounding explanations** over bullet dumps.
- When work is done, give a plain-language summary he can reuse in Dr. Campbell check-ins.
- Surface any discrepancy between this brief and the real code rather than silently working around it.

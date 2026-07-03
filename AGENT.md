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
4. **Every film opens and closes** with the collection's designated opening/closing A-roll artifacts.
5. The **Brian Eno / *Brain One*** framing lives only in `docs/` and the research report — keep it out of code.
6. **Do not build the frontend before the pipeline is validated end-to-end** (§5).
7. **Preserve the locked terminology** (§3) exactly.

---

## 3. Terminology (locked)

- **Artifact** — an individual media clip.
- **Collection** — a full curated set of artifacts (has designated opening + closing A-roll).
- **Film** — a generated output.
- **A-roll** — synchronized audio + video; stands alone.
- **B-roll** — video only; must always be paired with X-roll.
- **X-roll** — audio only; layered over B-roll.

Collection class hierarchy: `CL-AV` (A-roll), `CL-V` (B-roll), `CL-A` (X-roll).

---

## 4. Current state (verify on first run)

Engine package version **2.0.0**. The juxtaposition rewrite is implemented in code.

**Real file tree (excluding `.git`):**
```
dynamic-documentary-engine/
├── engine/
│   ├── __init__.py            # exports the public API (see §8)
│   ├── sequencer.py           # Sequencer — top-level coordinator
│   ├── collection_loader.py   # CollectionLoader — loads/validates a collection index
│   ├── rules.py               # SequencingRules — eligibility, no-repeat, duration budget, pacing
│   ├── artifact_selector.py   # ArtifactSelector — dissimilarity scoring + juxtaposition
│   └── assembler.py           # Assembler — FFmpeg rendering pipeline (lives here, NOT in pipeline/)
├── metadata/
│   ├── artifact_schema.json           # per-artifact schema (Draft-07, allOf conditional validation)
│   ├── collection_index_schema.json   # schema for a full collection index
│   ├── ww2_av_003_example.json        # example A-roll artifact
│   └── ww2_bv_live_001_example.json   # example B-roll (live-stream) artifact
├── docs/
│   ├── comparative_analysis_brain_one.md
│   └── sketches/*.jpg
├── README.md   # PARTLY STALE — see §7
└── LICENSE     # MIT
```

**Key behaviors already in code:**
- `rules.py` — `PACING_ARC`/`position_ratio` removed; `get_target_pacing()` signals A-roll/B-roll alternation (media-type variety) rather than a predetermined arc. Also enforces no-repeat, duration budget, and must-not-follow rules.
- `artifact_selector.py` — mood-transition logic removed; `_compute_dissimilarity_score()` + `_apply_juxtaposition_filter()` pick the **most unlike** next artifact across mood, pacing, tags, theme, geography, dominant lines. Top `_JUXTAPOSITION_POOL_SIZE` (=3) candidates go to weighted-random selection; `_last_selected` tracked internally.
- `assembler.py` — class-based FFmpeg pipeline; handles mixed sequences (strings = A-roll IDs, tuples = B-roll/X-roll pairs), local-file and live-stream sources, layers X-roll over B-roll (`-stream_loop -1`, `-shortest`), writes uniquely-named MP4s.
- `artifact_schema.json` — `file` object carries `source_type` ("local" | "stream") and `stream_url`; `allOf` conditional validation enforces per-type required fields.

**What does NOT exist yet in this repo (don't assume it does):**
- No `tests/` and no test files. (Any "tests passing" notes refer to work outside this repo — treat the pipeline as **not yet validated here**.)
- No collection-index file — only the index *schema* and two single-artifact examples. An end-to-end run needs a real collection index built first.
- No `pipeline/`, `web/`, `films/`, or `assets/` directories.

**Known pre-existing bug (not from recent edits):** in `artifact_schema.json`, nullable example fields (`file.stream_url`, `file.filename`, `ai_enrichment.enrichment_date`, `ai_enrichment.confidence_score`) are typed as plain `string`/`number`, but the example artifacts set them to `null`. Either the types should be `["string", "null"]` / `["number", "null"]`, or the examples shouldn't include those keys when unused. Confirm intended direction with David before changing.

---

## 5. Build sequence (in order)

1. Build a **diverse, multi-category** validation collection (10–20 artifacts) + its collection-index JSON.
2. Write an **end-to-end test script**: collection → `Sequencer.generate()` → `Assembler.render()` → film, printing the chosen sequence and why each pick was most dissimilar.
3. Flask backend.
4. React frontend.
5. Technical documentation report (where the Brian Eno / *Brain One* framing is used).

Never build a later stage before the earlier ones are validated.

> **Data note:** validation data is intentionally **cross-category** (e.g. war, nature, archival, modern, somber, absurd) — NOT single-theme. Wide variety gives the dissimilarity scoring more contrast and is a stronger test of the juxtaposition logic. (The `ww2_*` example files are legacy naming, not a mandate to stay WW2-only.)

---

## 6. Immediate next task (start here)

1. **Build a small collection index + validation collection** conforming to `collection_index_schema.json` and `artifact_schema.json`, using diverse multi-category artifacts (start with placeholder/local media paths if real assets aren't ready).
2. **Write an end-to-end validation script** that runs that collection through the real API (§8) and produces a film, printing a readable trace of the selected sequence and the dissimilarity reasoning at each cut. Match the **actual** signatures in the code — read the files first.

Optional adjacent cleanup, only if David approves: fix the nullable-field schema bug noted in §4.

Confirm with David before starting backend work.

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

- `Sequencer.generate()` returns a mixed sequence: strings for A-roll IDs, tuples for B-roll/X-roll pairs.
- `CollectionLoader` exposes `get_artifacts()`, `get_opening_artifact_id()`, `get_closing_artifact_id()`, `get_body_artifacts()`, `get_runtime_rules()`.
- `SequencingRules`: `is_eligible()`, `get_target_pacing()`, `register_selection()`, `has_reached_minimum_duration()`, `has_reached_maximum_duration()`, `reset()`.

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

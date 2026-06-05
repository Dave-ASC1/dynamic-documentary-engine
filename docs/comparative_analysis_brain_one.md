# Brain One vs Dynamic Documentary Engine — A Comparative Analysis

**Project:** Dynamic Documentary Engine
**Author:** Oluwafemisola (David)
**Institution:** Penn State University, College of IST
**Supervisor:** Dr. Betsy Campbell, Associate Teaching Professor
**Version:** 1.0.0

---

## 1. Introduction

The Dynamic Documentary Engine does not exist in a vacuum. It was directly inspired by Brain One — the generative engine built by creative technologist Brendan Dawes for the *Eno* documentary (2024), directed by Gary Hustwit. Brain One demonstrated something remarkable: that a documentary film could be assembled algorithmically at runtime, producing a different cut at every screening, with no two audiences ever watching the same film.

That proof of concept raised a deeper question — one that this project attempts to answer: *what happens when you take that idea, generalize it beyond a single film, give it emotional intelligence, open it to any collection of media, and make it available to anyone?*

This document provides an honest and detailed comparison of the two systems — what they share, where they diverge, and what the Dynamic Documentary Engine contributes to the field that Brain One did not set out to address. The debt to Brain One is acknowledged fully and without reservation. This project builds on that foundation rather than competing with it.

---

## 2. What Both Engines Share

Before examining the differences, it is important to acknowledge the common ground. The Dynamic Documentary Engine and Brain One share the same fundamental concept:

- **Generative documentary assembly** — both engines assemble documentary films from pre-edited media modules at runtime rather than in a traditional editing suite
- **No two screenings are identical** — every run of either engine produces a unique film, even from the same source material
- **Modular media as input** — both systems treat media as discrete, reusable modules rather than a single locked cut
- **Runtime as authorship** — the act of assembly is itself a creative act, happening live rather than being pre-determined
- **Viewer passivity** — in both systems the viewer has no control over what they watch; the engine decides
- **Human authorship at the collection level** — in both systems a human curates the raw material before the engine takes over

These shared foundations are not coincidental — the Dynamic Documentary Engine was consciously designed to honor and extend the generative documentary philosophy that Brain One introduced.

---

## 3. Key Differences

The following table summarizes the most significant differences between the two systems:

| Area | Brain One | Dynamic Documentary Engine |
|------|-----------|---------------------------|
| Selection logic | Deterministic algorithm | AI-driven (Claude API) |
| Scope | Single film — *Eno* (2024) | Any collection, any subject |
| Metadata approach | Structural and timing based | Mood, theme, pacing, tags, emotional transitions |
| Codebase | Proprietary, not publicly available | Open source, MIT licensed |
| Documentation | Not publicly documented | Fully documented, targets academic publication |
| Media types supported | Video segments | A-roll, B-roll, X-roll (audio only) |
| Transition logic | Fixed programmatic rules | Mood-aware, weighted random selection |
| Authorship model | Implicit — not theorized | Explicitly theorized — human as curator, AI as director |
| Output preservation | Screenings not systematically saved | Every generated film saved as an analytical artifact |
| Ethical sourcing | Licensed footage from single production | Copyright clearance built into metadata schema |
| Scale vision | Single production, closed system | Open-world retrieval — designed for internet-scale sources |
| Accessibility | Proprietary, requires custom build | Open source — reproducible by any researcher |

---

## 4. The Authorship Question — Human as Curator, AI as Director

One of the most intellectually significant differences between the two systems is not technical — it is philosophical. Brain One does not publicly address the question of authorship. The engine exists and produces films, but the question of *who is the author* is left implicit.

The Dynamic Documentary Engine confronts this question directly.

At first glance the answer seems simple — if the AI is making all the selection decisions, the AI is the director. But that framing is incomplete. Consider what happens before the engine ever runs: a human decides which clips belong in the collection. A human decides what gets tagged as "somber" versus "tense." A human designates which artifact opens every film and which closes it. A human defines the runtime rules. That is authorship — even if the AI decides everything that happens in between.

The more precise and defensible framing is this: **the human is the curator, the AI is the director.**

The human curates the collection — establishing the creative vocabulary, the emotional range, the thematic boundaries of what the engine can draw from. The AI directs the film — making real-time decisions about selection, ordering, pacing, and emotional arc within that vocabulary.

This is not unlike how a human film director works. The director does not shoot every frame. A cinematographer, a producer, an archive researcher all contribute material. The director's vision shapes how that material is assembled. In the Dynamic Documentary Engine, the collection *is* the director's vision. The AI is the editor executing it.

This framing — human as curator, AI as director — is a deliberate design philosophy and a meaningful conceptual contribution that Brain One never articulated.

---

## 5. Emotional Arc Modeling

Brain One's primary contribution is structural variety — different cuts, different timings, different segment orders. The focus is on making the film *different* each time it runs.

The Dynamic Documentary Engine takes a fundamentally different approach. Rather than optimizing for structural variety alone, it models *emotional arc* — the way a film's mood shifts and develops across its runtime.

Every artifact in a collection is tagged with a mood value: somber, tense, hopeful, neutral, triumphant, melancholic, urgent, or reflective. The artifact selector uses a mood transition matrix to guide selection — after a "somber" clip, it naturally prefers "reflective" or "melancholic" over "triumphant." After "tense," it gravitates toward "urgent" or "somber" before opening into "neutral."

The result is a film that does not just feel different from its last run — it feels *intentional*. The emotional journey has shape. It rises and falls. It creates meaning through juxtaposition rather than just variety through randomness.

This distinction matters enormously for documentary filmmaking specifically. A documentary is not just a sequence of images — it is an argument, an emotional experience, a point of view. Structural variety alone does not produce that. Emotional arc modeling is what separates a generative documentary from a generative slideshow.

---

## 6. Reproducibility and Analytical Value

Brain One's generated films are experiential — they happen in a theater, they are watched, and they disappear. There is no systematic record of what the engine selected, in what order, or why. The film cannot be studied after the fact. It can only be experienced in the moment.

This is a deliberate and artistically valid choice for a theatrical context. But it means Brain One cannot be studied as a system. The decisions it makes are opaque and ephemeral.

The Dynamic Documentary Engine takes the opposite position. Every generated film is saved as an analytical artifact — a permanent record of what the engine selected, in what order, for how long, and under what metadata conditions. Those artifacts can be reviewed, critiqued, compared across runs, and used as evidence in research.

This transforms the engine from a creative tool into a research instrument. It becomes possible to ask and answer questions that Brain One cannot address:

- Does the mood transition logic produce emotionally coherent films?
- Does weighted selection produce meaningfully different results from uniform random selection?
- How does runtime length affect the perceived quality of the generated film?
- What patterns emerge across multiple generations from the same collection?

These are scientific questions. Saving generated films as analytical artifacts is what makes them answerable. That is a research contribution Brain One never aimed for — and it is central to what makes this project an academic internship rather than just a creative experiment.

---

## 7. Ethical Sourcing by Design

Brain One was built for a major documentary production with access to licensed footage, a production budget, and legal clearance handled at the production level. Ethical sourcing was not a design concern for the engine itself — it was handled upstream by the production.

The Dynamic Documentary Engine cannot make that assumption. It is designed to be used by anyone, with any collection, including researchers and students who do not have access to licensed footage or production budgets.

For this reason, ethical sourcing is built into the metadata schema at the artifact level — not treated as an external concern. Every artifact carries two fields that address this directly:

- **`source`** — identifies the origin of the artifact: self-recorded, public-domain, or live-webcam
- **`copyright_cleared`** — a boolean flag confirming the artifact is cleared for use in the project

This means the engine itself can enforce sourcing rules — refusing to assemble a film that includes an artifact that has not been cleared. It also means the provenance of every artifact in every generated film is permanently documented, which matters for academic publication and gallery submission.

This is not a minor technical detail. It is what makes the engine usable and trustworthy outside of a controlled production environment.

---

## 8. Vision — Open-World Retrieval

The current implementation of the Dynamic Documentary Engine is a **closed-world system** — it works with whatever artifacts are manually placed into a collection. For the proof-of-concept phase this is appropriate. A collection of 10 to 20 carefully tagged clips is sufficient to validate the core architecture and demonstrate the sequencing logic.

But the long-term vision is significantly more ambitious.

### Phase 1 — Closed-World (Current)
The engine works with a fixed, manually curated collection. Artifacts are self-recorded or sourced from public domain repositories and tagged by hand or with AI assistance. The collection is finite and known in advance.

### Phase 2 — Open-World Retrieval (Future Vision)
The engine reaches out to public domain archives at runtime and assembles films from effectively unlimited material. The collection becomes a **filter and ruleset** rather than a fixed library — a set of metadata criteria the engine uses to query external sources and retrieve matching artifacts dynamically.

Potential sources for open-world retrieval include:
- **Internet Archive (archive.org)** — one of the largest public domain media repositories in the world, containing historical footage, audio recordings, and films
- **Wikimedia Commons** — verified free media across all categories
- **Library of Congress** — digitized historical footage and audio
- **NASA and NOAA** — all government-produced media is public domain by law
- **Free Music Archive and ccMixter** — Creative Commons licensed audio for X-roll
- **YouTube Creative Commons** — filtered CC licensed video content

In an open-world system, every generated film potentially combines artifacts that have never been placed together in the history of filmmaking. The creative space becomes effectively infinite. A collection is no longer a box of clips — it is a description of a film waiting to be found.

This vision has not been implemented in any publicly documented generative documentary system. Brain One works with a fixed set of footage from a single production. The open-world retrieval concept represents a genuinely new direction for the field — one that this project is designed to grow into, even if Phase 1 is where it begins.

---

## 9. Democratization

Brain One required a custom proprietary system designed and built by Brendan Dawes — an experienced creative technologist with decades of work at the intersection of code and art — for a professionally produced feature documentary with a full production team and budget behind it.

The bar for replicating or building on Brain One is extremely high. The codebase is not public. The methodology is not documented. A researcher wanting to explore generative documentary filmmaking cannot start from Brain One — they have to start from scratch.

The Dynamic Documentary Engine is designed to change that.

Built by a single undergraduate researcher using open tools — Python, FFmpeg, a public API — the entire system is open source, MIT licensed, and fully documented. Every design decision is explained. Every component is modular and replaceable. The metadata schema is a published standard that anyone can adopt.

If this project works, a filmmaker, researcher, educator, or student anywhere in the world can clone the repository, drop in their own collection, and generate their first film in an afternoon. No proprietary tools. No production budget. No gatekeeping.

That democratization of the generative documentary concept is not a side effect of the project — it is one of its core goals.

---

## 10. Honest Limitations

Academic credibility requires honesty about where Brain One is likely still ahead.

**Production quality and real-world testing**
Brain One has been tested in actual theatrical screenings with real audiences watching a real film. The Dynamic Documentary Engine has not. The gap between a working prototype and a production-ready system is significant and should not be minimized.

**Scale and refinement**
Brain One has had years of development and refinement. This engine is a summer prototype. There will be edge cases, bugs, and sequencing decisions that produce poor results. That is expected and acceptable at this stage — but it is worth naming honestly.

**Creative expertise**
Brendan Dawes brings decades of experience as a creative technologist. The aesthetic and experiential quality of Brain One reflects that expertise. This project makes no claim to match that quality at this stage.

**Unknown internals**
Because Brain One is proprietary and undocumented, some comparisons in this document are based on publicly available information about the *Eno* documentary and interviews with its creators. It is possible that Brain One incorporates features or approaches not captured here.

Acknowledging these limitations does not weaken the case for the Dynamic Documentary Engine. It strengthens it — by demonstrating that the claims made elsewhere in this document are measured, honest, and grounded in reality rather than overclaimed.

---

## 11. Conclusion

Brain One proved that the generative documentary was possible. It showed that a film could be assembled by an algorithm, that no two screenings needed to be identical, and that the experience could be meaningful and moving for a real audience.

The Dynamic Documentary Engine asks the next set of questions. What if the engine understood emotion, not just structure? What if it worked for any collection, not just one film? What if it saved its decisions so they could be studied? What if it was built in the open so anyone could use it? What if its ambition extended to drawing from the entire public domain — assembling films from material that has never been combined before?

Brain One is the foundation. This project is what gets built on top of it.

---

*For technical implementation details see the project README and metadata schema documentation in this repository.*
*For the full codebase see the `engine/` directory.*

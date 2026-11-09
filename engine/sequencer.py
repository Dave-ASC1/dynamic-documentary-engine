"""
sequencer.py
------------
Dynamic Documentary Engine — Main Sequencing Engine

The core of the Dynamic Documentary Engine. Orchestrates the full
film generation process by coordinating the collection loader,
sequencing rules, and artifact selector to produce a unique ordered
sequence of artifacts on every run.

All sequencing logic is creative code — no external AI engines are used.
Selection decisions are driven entirely by metadata rules, dissimilarity
scoring, and weighted random selection.

Usage:
    from engine.sequencer import Sequencer

    sequencer = Sequencer("metadata/collections/wwii_collection_index.json")
    film = sequencer.generate(target_duration=1800)
    print(film)

Author: Oluwafemisola (David)
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.1.0
"""

import random

from engine.collection_loader import CollectionLoader
from engine.context import ScreeningContext, shared_labels
from engine.rules import SequencingRules
from engine.artifact_selector import ArtifactSelector


class Sequencer:
    """
    The main sequencing engine for the Dynamic Documentary Engine.

    Coordinates the full film generation pipeline:
        1. Loads a collection index from disk
        2. Accepts a target runtime in seconds (4-digit max: 0001–9999)
        3. Opens with a generated B-roll + X-roll pair — or, with memory
           triggers on, with the clip that best matches the screening
        4. Selects body artifacts using rules, dissimilarity, and weights —
           or, with memory triggers on, by their labels (see below)
        5. Enforces B-roll + X-roll pairing — B-roll is never placed alone
        6. Closes with a generated B-roll + X-roll pair
        7. Returns the complete ordered film sequence

    Memory films:
        When generate() is given a screening context (memory triggers), the
        clips' labels drive the film instead of chance: it opens on the
        best match for the screening's date, season or cue, the other
        matches follow strongest first, and from then on each clip leads to
        one sharing a person, place, tag, theme or mood with it. Contrast
        takes over only where nothing shares a label. See engine/context.py.

    Runtime Control:
        target_duration accepts values from 1 to 9999 seconds, supporting
        both short-form clips and full-length feature documentaries.

    B-roll / X-roll Pairing:
        B-roll artifacts carry video but no audio. Whenever a B-roll artifact
        is selected, the engine immediately pairs it with an X-roll artifact
        to provide the audio layer. A-roll artifacts stand alone.

    Each call to generate() produces a unique film sequence. No two
    generated films are guaranteed to be identical.

    Attributes:
        collection_path (str): Path to the collection index JSON file.
        loader (CollectionLoader): The collection loader instance.
        collection (dict): The loaded collection data.
        rules (SequencingRules): The active sequencing rules.
        selector (ArtifactSelector): The artifact selector instance.
    """

    # Minimum and maximum allowed target duration in seconds.
    # Four digits supports both short-form (1s) and feature-length (9999s ~ 2.7 hrs).
    MIN_DURATION = 1
    MAX_DURATION = 9999

    def __init__(
        self,
        collection_path,
        diversity_mode=False,
        usage_counts=None,
        juxtaposition_pool_size=None,
    ):
        """
        Initializes the Sequencer with a path to a collection index.

        Args:
            collection_path (str): Path to the collection index JSON file.
            diversity_mode (bool): If True, underused artifacts receive a
                selection-weight boost while contrast ordering is preserved.
            usage_counts (dict): Cross-run artifact usage counts for diversity mode.
            juxtaposition_pool_size (int): Optional number of top contrast
                candidates eligible for weighted selection.

        Raises:
            FileNotFoundError: If the collection index file does not exist.
            ValueError: If the collection index is missing required fields.
        """
        self.collection_path = collection_path
        self.generated_usage = {}
        # Screening-context results of the last generate() call.
        self.memory = None
        self.context_matches = {}

        self.loader = CollectionLoader(collection_path)
        self.collection = self.loader.load()

        runtime_rules = self.loader.get_runtime_rules()
        self.rules = SequencingRules(runtime_rules)
        self.selector = ArtifactSelector(
            self.rules,
            diversity_mode=diversity_mode,
            usage_counts=usage_counts,
            juxtaposition_pool_size=juxtaposition_pool_size,
        )

    def generate(self, target_duration=None, allow_overshoot=False, context=None):
        """
        Generates a unique ordered film sequence from the loaded collection.

        Without a screening context, the sequence begins and ends with
        generated B-roll + X-roll pairs drawn from the normal body artifact
        pool, and body artifacts between those bookends are selected from
        any eligible A-roll or B-roll using dissimilarity scoring and
        weighted random selection.

        With a screening context it is a memory film (see the class
        docstring): it opens on the best-matching clip, the other matches
        follow, and the rest follows the clips' shared labels.

        B-roll artifacts are always paired with an X-roll artifact to provide
        an audio layer. A-roll artifacts stand alone.

        Args:
            target_duration (int, optional): Desired film runtime in seconds.
                                             Must be between 1 and 9999.
                                             Supports short-form and feature-length films.
                                             If not provided, uses the collection's
                                             max_duration_seconds runtime rule.
            allow_overshoot (bool, optional): By default the closing B-roll's
                                             duration is reserved in the
                                             budget before body selection, so
                                             whole clips alone never exceed
                                             target_duration. Set True to skip
                                             that reservation and let the
                                             total land at or slightly past
                                             target_duration instead — for
                                             callers that will trim the
                                             rendered film down to an exact
                                             length afterward, where having
                                             real footage past the target to
                                             cut is the point.
            context (ScreeningContext | dict, optional): The screening's
                                             date, season and any cues — turns
                                             the run into a memory film. After
                                             the call, self.memory describes
                                             the clip the film opened on (or
                                             is None when nothing matched),
                                             self.triggered lists every
                                             matching clip that played, in
                                             order, and self.context_matches
                                             maps each matching artifact ID to
                                             (points, reasons). None leaves
                                             generation exactly as without it.

        Returns:
            list: An ordered list of artifact ID strings and paired tuples.
                  B-roll entries are tuples: ('broll_id', 'xroll_id').
                  A-roll entries are plain strings.

        Raises:
            ValueError: If target_duration is outside the 1–9999 second range.
            RuntimeError: If the collection cannot produce generated bookends.
        """
        if target_duration is not None:
            if not (self.MIN_DURATION <= target_duration <= self.MAX_DURATION):
                raise ValueError(
                    f"target_duration must be between {self.MIN_DURATION} and "
                    f"{self.MAX_DURATION} seconds. Got: {target_duration}"
                )
            self.rules.runtime_rules["max_duration_seconds"] = target_duration

        self.rules.reset()
        self.generated_usage = {}
        sequence = []

        body_artifacts = self.loader.get_body_artifacts()
        if not body_artifacts:
            raise RuntimeError(
                "Collection has no body artifacts available for selection."
            )

        # Score every artifact against the screening context up front. The
        # selector also boosts matching artifacts' weights wherever a choice
        # is still drawn by weight (bookends, audio, ties).
        if isinstance(context, dict):
            context = ScreeningContext.from_dict(context)
        memory_film = context is not None
        self.memory = None
        self.triggered = []
        self.context_matches = {}
        if memory_film:
            for a in body_artifacts:
                points, reasons = context.match(a)
                if points:
                    self.context_matches[a.get("artifact_id")] = (points, reasons)
        self.selector.context_scores = {
            artifact_id: points
            for artifact_id, (points, _reasons) in self.context_matches.items()
        }
        # In a memory film, B-roll with a mood gets audio of the same mood.
        self.selector.match_audio_mood = memory_film

        b_roll_artifacts = [
            a for a in body_artifacts if a.get("artifact_type") == "B-roll"
        ]
        x_roll_artifacts = [
            a for a in body_artifacts if a.get("artifact_type") == "X-roll"
        ]

        if not b_roll_artifacts or not x_roll_artifacts:
            raise RuntimeError(
                "Generated bookends require at least one B-roll artifact and "
                "one X-roll artifact in the body pool."
            )

        # Step 1 — Open. A memory film opens on the clip that best matches
        # the screening. Otherwise, or when nothing matches, the film opens
        # on a generated B-roll + X-roll pair from the body pool.
        opener = None
        if memory_film:
            opener = self._best_context_match(body_artifacts, x_roll_artifacts)
            if opener is not None:
                self._place_opener(opener, sequence, body_artifacts)

        if opener is None:
            opening_pair = self._select_random_broll_xroll_pair(
                b_roll_artifacts,
                x_roll_artifacts,
            )
            if opening_pair is None:
                raise RuntimeError("Could not generate an opening B-roll/X-roll pair.")

            opening_broll, opening_xroll = opening_pair
            sequence.append((
                opening_broll.get("artifact_id"),
                opening_xroll.get("artifact_id"),
            ))
            self.rules.register_selection(opening_broll)
            self.rules.register_pairing_selection(opening_xroll)
            self._record_generated_usage(opening_broll)
            self._record_generated_usage(opening_xroll)
            self.selector.set_previous_artifact(opening_broll)
            opener = opening_broll

        # Reserve the closing pair before body selection so the body cannot
        # consume every B-roll/X-roll and leave the film without an ending.
        # When some clips match the screening, the close is drawn from the
        # ones that don't if it can be, so the matches stay free to follow
        # the opening rather than being held back for the last shot.
        closing_pair = None
        if self.context_matches:
            closing_pair = self._select_random_broll_xroll_pair(
                [a for a in b_roll_artifacts
                 if a.get("artifact_id") not in self.context_matches],
                x_roll_artifacts,
            )
        if closing_pair is None:
            closing_pair = self._select_random_broll_xroll_pair(
                b_roll_artifacts,
                x_roll_artifacts,
            )
        if closing_pair is None:
            raise RuntimeError("Could not generate a closing B-roll/X-roll pair.")

        reserved_closing_ids = {a.get("artifact_id") for a in closing_pair}

        # Reserve the closing B-roll's screen time in the duration budget so
        # the body loop leaves room for it. Without this, the loop only
        # budgets against the requested max, the close gets appended after
        # the loop with no budget check of its own, and the film reliably
        # overshoots target_duration by however long the closing clip is.
        # Skipped entirely in allow_overshoot mode, where landing at or
        # past target_duration using whole clips is the intended behavior.
        closing_broll, _closing_xroll_for_budget = closing_pair
        requested_max = self.rules.runtime_rules.get("max_duration_seconds", float("inf"))
        if not allow_overshoot:
            self.rules.runtime_rules["max_duration_seconds"] = max(
                0, requested_max - closing_broll.get("duration_seconds", 0)
            )

        # Step 2 — Select body artifacts until target duration is reached.
        standalone_candidates = [
            a for a in body_artifacts
            if (
                a.get("artifact_type") != "X-roll"
                and a.get("artifact_id") not in reserved_closing_ids
            )
        ]

        current_mood = opener.get("mood")

        while not self.rules.has_reached_maximum_duration():

            if memory_film:
                selected = self._select_memory_film_next(standalone_candidates)
            else:
                target_pacing = self.rules.get_target_pacing()
                selected = self.selector.select_next(
                    standalone_candidates,
                    current_mood=current_mood,
                    target_pacing=target_pacing
                )

            if selected is None:
                break

            artifact_type = selected.get("artifact_type")

            if artifact_type == "B-roll":
                # The closing pair's B-roll is held back so the film has an
                # ending to reach, but its X-roll is not: audio may be
                # reused within a film, so reserving it buys nothing and
                # costs variety. With only two or three recordings in a
                # collection, excluding one removed a third of the available
                # audio from every body slot — the reserved track ended up
                # heard only in the bookends and nowhere else.
                x_roll_pool = [
                    a for a in body_artifacts
                    if a.get("artifact_type") == "X-roll"
                ]
                x_roll = self.selector.select_pairing(x_roll_pool)

                if x_roll:
                    sequence.append((
                        selected.get("artifact_id"),
                        x_roll.get("artifact_id"),
                    ))
                    self._record_generated_usage(selected)
                    self._record_generated_usage(x_roll)
                else:
                    continue
            else:
                sequence.append(selected.get("artifact_id"))
                self._record_generated_usage(selected)

            self._record_triggered(selected, len(sequence) - 1)
            current_mood = selected.get("mood")

        # Restore the true requested max now that the reserved room has done
        # its job — register_selection() below doesn't consult the budget,
        # this is just so runtime_rules reflects the real target afterward.
        self.rules.runtime_rules["max_duration_seconds"] = requested_max

        # Step 3 — Close with the reserved generated B-roll + X-roll pair.
        closing_broll, closing_xroll = closing_pair
        sequence.append((
            closing_broll.get("artifact_id"),
            closing_xroll.get("artifact_id"),
        ))
        self.rules.register_selection(closing_broll)
        self.rules.register_pairing_selection(closing_xroll)
        self._record_generated_usage(closing_broll)
        self._record_generated_usage(closing_xroll)
        self._record_triggered(closing_broll, len(sequence) - 1)

        return sequence

    def _record_generated_usage(self, artifact):
        """
        Records that an artifact appeared in the generated film.

        Args:
            artifact (dict): Artifact summary dictionary.
        """
        artifact_id = artifact.get("artifact_id")
        if artifact_id:
            self.generated_usage[artifact_id] = (
                self.generated_usage.get(artifact_id, 0) + 1
            )

    def _record_triggered(self, artifact, slot_index):
        """
        Notes a clip that matched the screening context, once it has a
        place in the sequence, so the result can say what was triggered.

        Args:
            artifact (dict):  The clip just placed.
            slot_index (int): Its position in the sequence.
        """
        match = self.context_matches.get(artifact.get("artifact_id"))
        if match:
            self.triggered.append({
                "artifact_id": artifact.get("artifact_id"),
                "points": match[0],
                "reasons": list(match[1]),
                "slot_index": slot_index,
            })

    def _select_random_broll_xroll_pair(self, b_roll_artifacts, x_roll_artifacts):
        """
        Selects a weighted-random B-roll + X-roll pair for generated bookends.

        This method does not register the artifacts. The caller decides when
        to charge the pair against rule state, which allows the closing pair
        to be reserved before body selection and appended at the end.

        Args:
            b_roll_artifacts (list): Candidate B-roll artifacts.
            x_roll_artifacts (list): Candidate X-roll artifacts.

        Returns:
            tuple: (b_roll, x_roll), or None if no complete pair is available.
        """
        b_candidates = [a for a in b_roll_artifacts if self.rules.is_eligible(a)]
        x_candidates = [
            a for a in x_roll_artifacts if self.rules.is_eligible_for_pairing(a)
        ]

        b_roll = self.selector.weighted_random_choice(b_candidates)
        if b_roll and self.selector.match_audio_mood:
            x_candidates = self.selector.same_mood(b_roll, x_candidates)
        x_roll = self.selector.weighted_random_choice(x_candidates)

        if not b_roll or not x_roll:
            return None

        return b_roll, x_roll

    def _best_context_match(self, body_artifacts, x_roll_artifacts):
        """
        Chooses the clip that best matches the screening context, for a
        memory film to open on.

        Only A-roll and B-roll qualify (X-roll can't stand alone, though a
        matching X-roll is still favoured as a B-roll's audio). Among the
        highest-scoring matches, one is drawn by weight. A B-roll is only
        chosen if at least one X-roll is allowed to sit under it.

        Args:
            body_artifacts (list):   All body artifacts.
            x_roll_artifacts (list): The X-roll pool, for the pairing check.

        Returns:
            dict: The best-matching clip, or None when nothing matches.
        """
        if not self.context_matches:
            return None

        candidates = []
        for a in body_artifacts:
            artifact_id = a.get("artifact_id")
            if artifact_id not in self.context_matches:
                continue
            if not self.rules.is_available(a):
                continue
            if a.get("artifact_type") == "B-roll" and not any(
                artifact_id not in x.get("must_not_follow", []) for x in x_roll_artifacts
            ):
                continue
            candidates.append(a)

        if not candidates:
            return None

        best = max(self.context_matches[a.get("artifact_id")][0] for a in candidates)
        strongest = [
            a for a in candidates if self.context_matches[a.get("artifact_id")][0] == best
        ]
        return self.selector.weighted_random_choice(strongest)

    def _place_opener(self, opener, sequence, body_artifacts):
        """
        Places the best-matching clip as the first shot of a memory film,
        pairing it with an X-roll if it is a B-roll, and records it in
        self.memory.

        Args:
            opener (dict):          The clip from _best_context_match().
            sequence (list):        The (empty) sequence being built.
            body_artifacts (list):  All body artifacts (for the X-roll pool).
        """
        opener_id = opener.get("artifact_id")
        points, reasons = self.context_matches[opener_id]
        self.selector.place(opener, kind="opening", reasons=list(reasons))
        self._record_generated_usage(opener)

        if opener.get("artifact_type") == "B-roll":
            x_roll_pool = [
                a for a in body_artifacts if a.get("artifact_type") == "X-roll"
            ]
            # _best_context_match only picks a B-roll that some X-roll may
            # sit under, so a pairing is always available here.
            x_roll = self.selector.select_pairing(x_roll_pool)
            sequence.append((opener_id, x_roll.get("artifact_id")))
            self._record_generated_usage(x_roll)
        else:
            sequence.append(opener_id)

        self.memory = {
            "artifact_id": opener_id,
            "points": points,
            "reasons": list(reasons),
            "slot_index": len(sequence) - 1,
            "placement": "opening",
        }
        self._record_triggered(opener, len(sequence) - 1)

    def _select_memory_film_next(self, candidates):
        """
        Chooses the next clip of a memory film, in order of preference:

            1. A clip that matches the screening and hasn't played yet —
               strongest match first; among equally strong ones, the one
               sharing the most labels with the clip just shown.
            2. A clip sharing a label (person, place, tag, theme or mood)
               with the clip just shown — the most shared labels first.
            3. Nothing shares a label: the usual pick by contrast.

        Ties are drawn by weight. Clips chosen by 1 or 2 are placed through
        the selector with the reason, so the trace can show why.

        Args:
            candidates (list): Standalone candidates (A-roll and B-roll).

        Returns:
            dict: The clip chosen and registered, or None if nothing fits.
        """
        eligible = [a for a in candidates if self.rules.is_eligible(a)]
        if not eligible:
            return None
        previous = self.selector.previous

        matched = [a for a in eligible if a.get("artifact_id") in self.context_matches]
        if matched:
            best = max(self.context_matches[a.get("artifact_id")][0] for a in matched)
            tier = [
                a for a in matched
                if self.context_matches[a.get("artifact_id")][0] == best
            ]
            pick, _shared = self._most_linked(previous, tier)
            reasons = self.context_matches[pick.get("artifact_id")][1]
            return self.selector.place(pick, kind="memory", reasons=list(reasons))

        pick, shared = self._most_linked(previous, eligible)
        if shared:
            return self.selector.place(pick, kind="flow", reasons=shared)

        return self.selector.select_next(candidates)

    def _most_linked(self, previous, pool):
        """
        The clip in pool sharing the most labels with previous, drawn by
        weight among equals.

        Args:
            previous (dict): The clip just shown, or None.
            pool (list):     Candidate clips (not empty).

        Returns:
            tuple: (clip, shared labels) — the labels are empty when
                   nothing in the pool shares one.
        """
        links = [(a, shared_labels(previous, a)) for a in pool]
        most = max(len(shared) for _a, shared in links)
        strongest = [a for a, shared in links if len(shared) == most]
        pick = self.selector.weighted_random_choice(strongest)
        return pick, next(shared for a, shared in links if a is pick)

    def generate_multiple(self, count, target_duration=None, context=None):
        """
        Generates multiple unique film sequences from the same collection.

        Each sequence is generated independently with no shared state,
        ensuring every film is unique.

        Args:
            count (int): The number of film sequences to generate.
            target_duration (int, optional): Desired runtime per film in seconds.
                                             Must be between 1 and 9999.
            context (ScreeningContext | dict, optional): Screening context
                                             applied to every film.

        Returns:
            list: A list of film sequences.
        """
        return [
            self.generate(target_duration, context=context) for _ in range(count)
        ]

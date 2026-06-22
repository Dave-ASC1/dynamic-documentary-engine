"""
artifact_selector.py
--------------------
Dynamic Documentary Engine — Artifact Selector

Responsible for selecting individual artifacts from a collection
during film generation. Uses dissimilarity scoring across all
descriptive metadata dimensions to maximise juxtaposition between
consecutive clips.

Design Philosophy:
    The selector's sole aesthetic directive is contrast. It does not try
    to find artifacts that "flow" from the previous one. It actively seeks
    the artifact that is LEAST like the one before it — different geography,
    different time period, different subject, different tags, different
    media type, different mood. The viewer should never feel settled.

    The previous MOOD_TRANSITIONS table and _apply_mood_preference() method
    have been removed entirely. They enforced emotional continuity — the
    opposite of what this engine is designed to produce.

    The previous _apply_pacing_preference() method has been replaced with
    _apply_media_type_variety(), which nudges selection toward alternating
    between A-roll and B-roll. This creates visual rhythm without imposing
    any emotional arc.

    Weighted random selection is preserved. Weight is a collection-designer
    tool for controlling relative frequency of appearance, not for emotional
    or tonal shaping.

Author: Oluwafemisola David Ademoye
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 2.0.0
"""

import random


class ArtifactSelector:
    """
    Selects the next artifact to add to a film sequence from a pool
    of eligible candidates.

    Selection is driven by maximum dissimilarity from the previous artifact
    across all available metadata dimensions, followed by weighted random
    selection within the most dissimilar candidates.

    The selector tracks the previously selected artifact internally so that
    dissimilarity scoring has access to the full artifact dict — geography,
    time_period, subject, tags, mood, pacing, and artifact_type — without
    requiring any changes to the sequencer.py interface.

    Attributes:
        rules (SequencingRules): The active rule engine for this session.
        _last_selected (dict):   The most recently selected artifact dict,
                                 or None if no selection has been made yet.
                                 Used as the comparison baseline for
                                 dissimilarity scoring.
    """

    # Number of top candidates (by dissimilarity score) passed to weighted
    # random selection. A value of 1 would always pick the single most
    # dissimilar artifact; higher values introduce controlled randomness
    # while still ensuring strong juxtaposition.
    # Set to 3: always choose from the top-3 most dissimilar candidates.
    _JUXTAPOSITION_POOL_SIZE = 3

    def __init__(self, rules):
        """
        Initializes the ArtifactSelector with an active rule engine.

        Args:
            rules (SequencingRules): The active sequencing rules for this session.
        """
        self.rules = rules
        self._last_selected = None

    def select_next(self, candidates, current_mood=None, target_pacing=None):
        """
        Selects the next artifact from a pool of candidates.

        Pipeline:
            1. Filter candidates through the rule engine for structural eligibility.
            2. If a previous artifact exists, score all eligible candidates by
               dissimilarity and sort descending (most different first).
            3. Apply media-type variety nudge using target_pacing as a signal
               from rules.get_target_pacing().
            4. Take the top _JUXTAPOSITION_POOL_SIZE candidates.
            5. Apply weighted random selection within that pool.
            6. Register the selection and update internal state.

        The current_mood parameter is accepted for interface compatibility with
        sequencer.py but is no longer used to guide selection toward emotionally
        similar artifacts. Mood is one of many dimensions scored by
        _compute_dissimilarity_score() — it contributes to contrast, not continuity.

        Args:
            candidates (list):       List of artifact dictionaries to select from.
            current_mood (str):      Mood of the previously selected artifact.
                                     Accepted for interface compatibility; not used
                                     to enforce mood continuity.
            target_pacing (str):     Pacing hint from rules.get_target_pacing().
                                     Interpreted as a media-type variety signal:
                                     'slow' = prefer A-roll, 'medium' = prefer B-roll,
                                     no override if pool is small.

        Returns:
            dict: The selected artifact dictionary, or None if no eligible
                  candidates are available.
        """
        eligible = [a for a in candidates if self.rules.is_eligible(a)]

        if not eligible:
            return None

        if self._last_selected is not None:
            # Score and sort by dissimilarity — most different first
            eligible = self._apply_juxtaposition_filter(eligible)

        # Apply media-type variety nudge within the dissimilarity-sorted pool
        eligible = self._apply_media_type_variety(eligible, target_pacing)

        # Take top candidates to maintain strong juxtaposition while
        # allowing weighted randomness within that tier
        top_candidates = eligible[:self._JUXTAPOSITION_POOL_SIZE]

        selected = self._weighted_random_select(top_candidates)

        if selected:
            self.rules.register_selection(selected)
            self._last_selected = selected

        return selected

    def select_by_type(self, candidates, artifact_type):
        """
        Filters candidates to a specific artifact type and selects one.

        Used by the sequencer when it needs to explicitly request a specific
        media type — most commonly when selecting an X-roll to pair with a
        B-roll slot. In this context, juxtaposition scoring still applies
        so the X-roll audio contrasts with the B-roll video.

        Args:
            candidates (list):    List of artifact dictionaries to filter.
            artifact_type (str):  The type to filter by — 'A-roll', 'B-roll',
                                  or 'X-roll'.

        Returns:
            dict: The selected artifact, or None if no eligible candidates
                  of that type exist.
        """
        typed_candidates = [
            a for a in candidates if a.get("artifact_type") == artifact_type
        ]
        return self.select_next(typed_candidates)

    # ------------------------------------------------------------------
    # Dissimilarity Scoring
    # ------------------------------------------------------------------

    def _compute_dissimilarity_score(self, previous: dict, candidate: dict) -> int:
        """
        Scores how dissimilar a candidate artifact is from the previous one.

        A higher score means the two artifacts are MORE different from each
        other. The selector uses this to find the most jarring possible cut.

        Scoring dimensions (each contributes 1 point per difference):
            - artifact_type differs (A-roll vs B-roll)
            - mood differs
            - pacing differs
            - No overlapping tags (each non-shared tag adds 1 point)
            - theme differs (no overlapping theme values)
            - geography differs (if present on both)
            - dominant_lines differ (if present on both)

        Note on tags and theme: these live inside the "content" sub-object
        in individual artifact JSON files, but at the top-level summary in
        the collection index (which is what the sequencer works with). Both
        locations are checked with fallback so the scorer works correctly
        regardless of whether full or summary artifact dicts are passed.

        Args:
            previous:  The previously selected artifact dict.
            candidate: The candidate artifact dict to score.

        Returns:
            Integer dissimilarity score. Higher = more different.
        """
        score = 0

        # --- Artifact type (A-roll vs B-roll) ---
        if previous.get("artifact_type") != candidate.get("artifact_type"):
            score += 1

        # --- Mood ---
        prev_mood = previous.get("mood") or previous.get("content", {}).get("mood")
        cand_mood = candidate.get("mood") or candidate.get("content", {}).get("mood")
        if prev_mood and cand_mood and prev_mood != cand_mood:
            score += 1

        # --- Pacing ---
        prev_pacing = previous.get("pacing") or previous.get("content", {}).get("pacing")
        cand_pacing = candidate.get("pacing") or candidate.get("content", {}).get("pacing")
        if prev_pacing and cand_pacing and prev_pacing != cand_pacing:
            score += 1

        # --- Tags: count non-overlapping tags on the candidate ---
        prev_tags = set(
            previous.get("tags") or previous.get("content", {}).get("tags", [])
        )
        cand_tags = set(
            candidate.get("tags") or candidate.get("content", {}).get("tags", [])
        )
        if prev_tags or cand_tags:
            # Unique tags on the candidate that the previous artifact did not have
            score += len(cand_tags - prev_tags)

        # --- Theme: count non-overlapping themes on the candidate ---
        prev_theme = set(
            previous.get("theme") or previous.get("content", {}).get("theme", [])
        )
        cand_theme = set(
            candidate.get("theme") or candidate.get("content", {}).get("theme", [])
        )
        if prev_theme or cand_theme:
            score += len(cand_theme - prev_theme)

        # --- Geography (from file.source or a top-level geography field) ---
        prev_geo = previous.get("geography") or previous.get("file", {}).get("geography")
        cand_geo = candidate.get("geography") or candidate.get("file", {}).get("geography")
        if prev_geo and cand_geo and prev_geo != cand_geo:
            score += 1

        # --- Dominant lines (visual composition) ---
        prev_lines = (
            previous.get("dominant_lines")
            or previous.get("content", {}).get("dominant_lines")
        )
        cand_lines = (
            candidate.get("dominant_lines")
            or candidate.get("content", {}).get("dominant_lines")
        )
        if prev_lines and cand_lines and prev_lines != cand_lines:
            score += 1

        return score

    def _apply_juxtaposition_filter(self, candidates: list) -> list:
        """
        Sorts candidates by dissimilarity score descending — most different first.

        Called only when self._last_selected is not None (i.e. after the
        first selection has been made). The sort is stable, preserving
        relative order among candidates with equal scores.

        Args:
            candidates: List of eligible artifact dicts.

        Returns:
            List of artifact dicts sorted most-to-least dissimilar from
            self._last_selected.
        """
        return sorted(
            candidates,
            key=lambda a: self._compute_dissimilarity_score(self._last_selected, a),
            reverse=True,   # Descending: most dissimilar first
        )

    # ------------------------------------------------------------------
    # Media-Type Variety
    # ------------------------------------------------------------------

    def _apply_media_type_variety(self, candidates: list, target_pacing: str) -> list:
        """
        Nudges the candidate pool to prefer alternating between A-roll and
        B-roll by surfacing the preferred type at the top of the list.

        This replaces the old _apply_pacing_preference() method. The pacing
        signal from rules.get_target_pacing() is repurposed here as a
        media-type variety hint (see rules.py get_target_pacing() docstring
        for the mapping). Non-preferred candidates remain available as
        fallbacks — this is a soft preference, not a hard filter.

        The nudge is applied AFTER juxtaposition sorting, so it only
        reorders within the already-sorted pool rather than overriding
        the dissimilarity ranking.

        Args:
            candidates:    Candidates already sorted by dissimilarity.
            target_pacing: Pacing hint from rules.get_target_pacing().
                           'slow' signals prefer A-roll.
                           'medium' signals prefer B-roll.
                           'fast' signals no media-type preference.

        Returns:
            List of candidates with the preferred media type surfaced first,
            followed by remaining candidates in their original order.
        """
        if target_pacing == "slow":
            preferred_type = "A-roll"
        elif target_pacing == "medium":
            preferred_type = "B-roll"
        else:
            # 'fast' or unrecognised: no media-type preference
            return candidates

        preferred = [a for a in candidates if a.get("artifact_type") == preferred_type]
        others = [a for a in candidates if a.get("artifact_type") != preferred_type]

        # Only apply the nudge if there are preferred candidates — never
        # remove the fallback pool, so the engine always has something to pick
        if preferred:
            return preferred + others

        return candidates

    # ------------------------------------------------------------------
    # Weighted Random Selection
    # ------------------------------------------------------------------

    def _weighted_random_select(self, candidates: list) -> dict:
        """
        Selects one artifact from candidates using weighted random selection.

        Artifacts with higher weight values (set by the collection designer
        in the sequencing metadata) are more likely to be selected. Weight
        is purely a frequency control tool — it has no emotional significance.

        If no weight is set on an artifact, a neutral default of 0.5 is used
        so all unweighted artifacts compete equally.

        Args:
            candidates: List of eligible artifact dicts (already filtered
                        and sorted by the juxtaposition pipeline).

        Returns:
            dict: The randomly selected artifact, or None if candidates is empty.
        """
        if not candidates:
            return None

        weights = [a.get("weight", 0.5) for a in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

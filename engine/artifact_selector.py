"""
artifact_selector.py
--------------------
Dynamic Documentary Engine — Artifact Selector

Responsible for selecting individual artifacts from a collection
during film generation. Uses metadata tags, mood, pacing, and
weighting to make context-aware selection decisions.

The selector works alongside the SequencingRules engine — rules
determine eligibility, the selector determines which eligible
artifact to pick next.

Author: Oluwafemisola David Ademoye
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import random


class ArtifactSelector:
    """
    Selects the next artifact to add to a film sequence from a pool
    of eligible candidates.

    Selection is driven by:
        - Artifact weight (higher weight = more likely to be selected)
        - Mood continuity (prefers artifacts that transition naturally)
        - Pacing arc (softly prefers artifacts matching the current film position)

    Attributes:
        rules (SequencingRules): The active rule engine for this session.
    """

    # Defines natural mood transition preferences.
    # Key = current mood, Value = list of preferred next moods in order.
    MOOD_TRANSITIONS = {
        "somber":      ["reflective", "melancholic", "neutral", "tense"],
        "tense":       ["urgent", "somber", "neutral", "reflective"],
        "hopeful":     ["neutral", "triumphant", "reflective", "somber"],
        "neutral":     ["somber", "reflective", "hopeful", "tense"],
        "triumphant":  ["hopeful", "neutral", "reflective", "somber"],
        "melancholic": ["somber", "reflective", "neutral", "hopeful"],
        "urgent":      ["tense", "somber", "neutral", "melancholic"],
        "reflective":  ["neutral", "somber", "melancholic", "hopeful"]
    }

    def __init__(self, rules):
        """
        Initializes the ArtifactSelector with an active rule engine.

        Args:
            rules (SequencingRules): The active sequencing rules for this session.
        """
        self.rules = rules

    def select_next(self, candidates, current_mood=None, target_pacing=None):
        """
        Selects the next artifact from a pool of candidates.

        Filters candidates through the rule engine for eligibility, then
        applies pacing arc and mood preference before using weighted random
        selection to pick the final artifact.

        Args:
            candidates (list): List of artifact dictionaries to select from.
            current_mood (str, optional): Mood of the previously selected artifact,
                                          used to guide mood transitions.
            target_pacing (str, optional): Desired pacing at this point in the film
                                           arc — 'slow', 'medium', or 'fast'.

        Returns:
            dict: The selected artifact dictionary, or None if no eligible
                  candidates are available.
        """
        eligible = [a for a in candidates if self.rules.is_eligible(a)]

        if not eligible:
            return None

        # Pacing preference is applied first — broader filter
        if target_pacing is not None:
            eligible = self._apply_pacing_preference(eligible, target_pacing)

        # Mood preference is applied second — finer filter within pacing group
        if current_mood:
            eligible = self._apply_mood_preference(eligible, current_mood)

        selected = self._weighted_random_select(eligible)

        if selected:
            self.rules.register_selection(selected)

        return selected

    def _apply_pacing_preference(self, candidates, target_pacing):
        """
        Reorders candidates to prefer artifacts matching the target pacing.
        Non-matching artifacts remain available as fallbacks.

        Args:
            candidates (list): List of eligible artifact dictionaries.
            target_pacing (str): Desired pacing — 'slow', 'medium', or 'fast'.

        Returns:
            list: Reordered candidates with matching pacing prioritized.
        """
        matching = [a for a in candidates if a.get("pacing") == target_pacing]
        non_matching = [a for a in candidates if a.get("pacing") != target_pacing]
        return matching + non_matching

    def _apply_mood_preference(self, candidates, current_mood):
        """
        Reorders candidates to prefer artifacts with moods that transition
        naturally from the current mood.

        Args:
            candidates (list): List of eligible artifact dictionaries.
            current_mood (str): Mood of the previously selected artifact.

        Returns:
            list: Reordered candidates with preferred transition moods prioritized.
        """
        preferred_moods = self.MOOD_TRANSITIONS.get(current_mood, [])
        preferred = [a for a in candidates if a.get("mood") in preferred_moods]
        non_preferred = [a for a in candidates if a.get("mood") not in preferred_moods]
        return preferred + non_preferred

    def _weighted_random_select(self, candidates):
        """
        Selects an artifact using weighted random selection.
        Artifacts with higher weight values are more likely to be selected.

        Args:
            candidates (list): List of eligible artifact dictionaries.

        Returns:
            dict: The randomly selected artifact, or None if candidates is empty.
        """
        if not candidates:
            return None
        weights = [a.get("weight", 0.5) for a in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    def select_by_type(self, candidates, artifact_type):
        """
        Filters candidates to a specific artifact type and selects one.

        Useful when the sequencing engine needs to explicitly select
        an A-roll, B-roll, or X-roll artifact at a specific point.

        Args:
            candidates (list): List of artifact dictionaries to filter.
            artifact_type (str): The type to filter by — 'A-roll', 'B-roll', or 'X-roll'.

        Returns:
            dict: The selected artifact, or None if no eligible candidates of that type exist.
        """
        typed_candidates = [
            a for a in candidates if a.get("artifact_type") == artifact_type
        ]
        return self.select_next(typed_candidates)

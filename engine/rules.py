"""
rules.py
--------
Dynamic Documentary Engine — Sequencing Rules

Defines the rule set that governs how the sequencing engine selects
and orders artifacts when assembling a generated film.

Rules are applied in order during artifact selection to ensure:
    - No artifact repeats within a single film (unless explicitly allowed)
    - Pacing varies naturally across the film arc
    - Mood transitions feel intentional rather than jarring
    - Total runtime stays within collection-defined bounds

Author: Oluwafemisola (David)
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""


class SequencingRules:
    """
    Defines and enforces the rules that govern artifact selection
    and ordering during film generation.

    Rules are evaluated against each candidate artifact before it
    is added to the film sequence. An artifact that fails any rule
    is skipped and the next candidate is evaluated.

    Attributes:
        runtime_rules (dict): The collection-level runtime rules.
        used_artifact_ids (list): Artifact IDs already selected in this session.
        current_duration (float): Total duration accumulated so far in seconds.
        position_ratio (float): Current position in the film as a value between
                                0.0 (start) and 1.0 (end). Used by pacing rules
                                to shape the emotional arc across the film runtime.
    """

    # Maps position in film to target pacing.
    # Films follow a natural arc: slow opening, building through the middle,
    # returning to slow or medium toward the close.
    PACING_ARC = [
        (0.0,  0.15, "slow"),     # Opening — establish tone slowly
        (0.15, 0.35, "medium"),   # Early middle — begin to build
        (0.35, 0.65, "fast"),     # Peak — highest energy section
        (0.65, 0.85, "medium"),   # Late middle — begin to wind down
        (0.85, 1.0,  "slow"),     # Closing — return to reflective pace
    ]

    def __init__(self, runtime_rules):
        """
        Initializes the SequencingRules with collection-level runtime rules.

        Args:
            runtime_rules (dict): The runtime rules from the collection index,
                                  including min/max duration and repeat settings.
        """
        self.runtime_rules = runtime_rules
        self.used_artifact_ids = []
        self.current_duration = 0.0
        self.position_ratio = 0.0

    def reset(self):
        """Resets rule state for a new film generation session."""
        self.used_artifact_ids = []
        self.current_duration = 0.0
        self.position_ratio = 0.0

    def is_eligible(self, artifact):
        """
        Evaluates whether an artifact is eligible for selection given
        the current state of the film sequence.

        An artifact is eligible if it passes all of the following rules:
            - No-repeat rule
            - Duration budget rule
            - Must-not-follow rule

        Pacing is enforced as a soft preference by the selector rather
        than a hard eligibility gate — see ArtifactSelector._apply_pacing_preference().

        Args:
            artifact (dict): The artifact summary dictionary to evaluate.

        Returns:
            bool: True if the artifact is eligible, False otherwise.
        """
        if not self._passes_no_repeat_rule(artifact):
            return False
        if not self._passes_duration_budget_rule(artifact):
            return False
        if not self._passes_must_not_follow_rule(artifact):
            return False
        return True

    def get_target_pacing(self):
        """
        Returns the target pacing for the current position in the film arc.

        Pacing follows a structured arc — slow at the opening, building
        through the middle, returning to slow toward the close.

        Returns:
            str: The target pacing — 'slow', 'medium', or 'fast'.
        """
        for start, end, pacing in self.PACING_ARC:
            if start <= self.position_ratio < end:
                return pacing
        return "medium"

    def _passes_no_repeat_rule(self, artifact):
        """Returns False if the artifact has already been used and cannot repeat."""
        artifact_id = artifact.get("artifact_id")
        can_repeat = artifact.get("can_repeat", False)
        if artifact_id in self.used_artifact_ids and not can_repeat:
            return False
        return True

    def _passes_duration_budget_rule(self, artifact):
        """Returns False if adding this artifact would exceed the maximum film duration."""
        max_duration = self.runtime_rules.get("max_duration_seconds", float("inf"))
        artifact_duration = artifact.get("duration_seconds", 0)
        if self.current_duration + artifact_duration > max_duration:
            return False
        return True

    def _passes_must_not_follow_rule(self, artifact):
        """
        Returns False if the previously selected artifact appears in
        this artifact's must_not_follow list.
        """
        must_not_follow = artifact.get("must_not_follow", [])
        if self.used_artifact_ids:
            if self.used_artifact_ids[-1] in must_not_follow:
                return False
        return True

    def _passes_pacing_rule(self, artifact, target_pacing):
        """Returns True if the artifact's pacing matches the target pacing."""
        return artifact.get("pacing") == target_pacing

    def register_selection(self, artifact):
        """
        Registers an artifact as selected and updates rule state.

        Updates current_duration and recalculates position_ratio so
        pacing rules stay accurate throughout film generation.

        Args:
            artifact (dict): The artifact dictionary that was selected.
        """
        self.used_artifact_ids.append(artifact.get("artifact_id"))
        self.current_duration += artifact.get("duration_seconds", 0)

        max_duration = self.runtime_rules.get("max_duration_seconds", 1)
        if max_duration > 0:
            self.position_ratio = min(self.current_duration / max_duration, 1.0)

    def has_reached_minimum_duration(self):
        """Returns True if the sequence has reached the minimum required runtime."""
        return self.current_duration >= self.runtime_rules.get("min_duration_seconds", 0)

    def has_reached_maximum_duration(self):
        """Returns True if the sequence has reached or exceeded the maximum runtime."""
        return self.current_duration >= self.runtime_rules.get("max_duration_seconds", float("inf"))

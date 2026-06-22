"""
rules.py
--------
Dynamic Documentary Engine — Sequencing Rules

Defines the rule set that governs how the sequencing engine selects
and orders artifacts when assembling a generated film.

Rules are applied in order during artifact selection to ensure:
    - No artifact repeats within a single film (unless explicitly allowed)
    - Pacing varies by alternating media types rather than following a
      predetermined emotional arc
    - Total runtime stays within collection-defined bounds

Design Philosophy:
    The engine imposes NO emotional arc, NO tonal continuity, and NO mood
    consistency of any kind. The viewer should be surprised — even shocked —
    by juxtaposition. A clip of soldiers marching may be followed immediately
    by birdsong. A burning village may cut to a waterfall. This contrast is
    not incidental; it is the engine's core aesthetic purpose.

    Accordingly, PACING_ARC has been removed. The engine no longer tracks
    position in a film or shapes an emotional curve. Pacing guidance from
    get_target_pacing() now serves only to encourage media-type variety
    (alternating A-roll and B-roll), not to enforce a predetermined feel.

    Mood and pacing metadata on artifacts remain in the schema for human
    reference and collection-design purposes only. The rule engine does not
    use them to enforce sequencing decisions.

Author: Oluwafemisola David Ademoye
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 2.0.0
"""


class SequencingRules:
    """
    Defines and enforces the structural rules that govern artifact selection
    and ordering during film generation.

    Rules are evaluated against each candidate artifact before it is added
    to the film sequence. An artifact that fails any rule is skipped and
    the next candidate is evaluated.

    What this class enforces (structural rules):
        - No-repeat: an artifact cannot appear twice unless can_repeat is True.
        - Duration budget: adding an artifact must not exceed max_duration_seconds.
        - Must-not-follow: an artifact can declare artifacts that must not
          directly precede it.

    What this class deliberately does NOT enforce:
        - Emotional arcs or mood continuity of any kind.
        - Pacing arcs tied to position in the film.
        - Tonal consistency or similarity between consecutive clips.

    Attributes:
        runtime_rules (dict):       The collection-level runtime rules.
        used_artifact_ids (list):   Artifact IDs already selected in this session,
                                    in selection order. Used for no-repeat and
                                    must-not-follow checks.
        current_duration (float):   Total duration accumulated so far in seconds.
        last_artifact_type (str):   The artifact_type of the most recently selected
                                    artifact ('A-roll', 'B-roll', or 'X-roll').
                                    Used by get_target_pacing() to encourage
                                    media-type variety between consecutive slots.
    """

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
        self.last_artifact_type = None

    def reset(self):
        """Resets rule state for a new film generation session."""
        self.used_artifact_ids = []
        self.current_duration = 0.0
        self.last_artifact_type = None

    def is_eligible(self, artifact):
        """
        Evaluates whether an artifact is eligible for selection given
        the current state of the film sequence.

        An artifact is eligible if it passes all of the following rules:
            - No-repeat rule
            - Duration budget rule
            - Must-not-follow rule

        No mood, pacing, or emotional checks are applied here. Those
        dimensions are not used by the rule engine.

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
        Returns a pacing hint to encourage media-type variety between slots.

        This method no longer drives an emotional arc. Instead, it signals
        to the ArtifactSelector which media type was used last, so the
        selector can prefer the opposite type for the next slot — alternating
        between A-roll and B-roll to create visual rhythm without imposing
        any predetermined emotional shape.

        The return values map to sequencer.py's expectations ('slow',
        'medium', 'fast') for interface compatibility, but the selector
        interprets them as media-type variety hints rather than emotional
        pacing targets.

        Mapping:
            last was A-roll  → return 'medium'  (prefer B-roll next)
            last was B-roll  → return 'slow'    (prefer A-roll next)
            no prior slot    → return 'medium'  (no preference)

        Returns:
            str: A pacing hint string — 'slow', 'medium', or 'fast'.
        """
        if self.last_artifact_type == "A-roll":
            return "medium"   # Signal: try B-roll next
        if self.last_artifact_type == "B-roll":
            return "slow"     # Signal: try A-roll next
        return "medium"       # No prior selection — no preference

    def _passes_no_repeat_rule(self, artifact):
        """
        Returns False if the artifact has already been used in this session
        and its can_repeat flag is not set to True.

        Args:
            artifact (dict): The artifact summary dictionary to check.

        Returns:
            bool: True if the artifact is allowed to be selected.
        """
        artifact_id = artifact.get("artifact_id")
        can_repeat = artifact.get("can_repeat", False)
        if artifact_id in self.used_artifact_ids and not can_repeat:
            return False
        return True

    def _passes_duration_budget_rule(self, artifact):
        """
        Returns False if adding this artifact would push the accumulated
        runtime over the collection's maximum allowed duration.

        Args:
            artifact (dict): The artifact summary dictionary to check.

        Returns:
            bool: True if this artifact fits within the remaining runtime budget.
        """
        max_duration = self.runtime_rules.get("max_duration_seconds", float("inf"))
        artifact_duration = artifact.get("duration_seconds", 0)
        if self.current_duration + artifact_duration > max_duration:
            return False
        return True

    def _passes_must_not_follow_rule(self, artifact):
        """
        Returns False if the most recently selected artifact appears in
        this artifact's must_not_follow list.

        This is a collection-designer-defined hard constraint. It exists
        for editorial reasons specific to a collection (e.g. two clips that
        are technically incompatible or factually contradictory) — not for
        mood or tonal reasons.

        Args:
            artifact (dict): The artifact summary dictionary to check.

        Returns:
            bool: True if this artifact is allowed to follow the previous one.
        """
        must_not_follow = artifact.get("must_not_follow", [])
        if self.used_artifact_ids:
            if self.used_artifact_ids[-1] in must_not_follow:
                return False
        return True

    def register_selection(self, artifact):
        """
        Registers an artifact as selected and updates rule state.

        Records the artifact ID in the used list, adds its duration to
        the running total, and updates last_artifact_type so that
        get_target_pacing() can encourage variety on the next selection.

        Args:
            artifact (dict): The artifact dictionary that was selected.
        """
        self.used_artifact_ids.append(artifact.get("artifact_id"))
        self.current_duration += artifact.get("duration_seconds", 0)
        self.last_artifact_type = artifact.get("artifact_type")

    def has_reached_minimum_duration(self):
        """
        Returns True if the sequence has met the minimum required runtime.

        Returns:
            bool: True if current_duration >= min_duration_seconds.
        """
        return self.current_duration >= self.runtime_rules.get("min_duration_seconds", 0)

    def has_reached_maximum_duration(self):
        """
        Returns True if the sequence has reached or exceeded the maximum runtime.

        Returns:
            bool: True if current_duration >= max_duration_seconds.
        """
        return self.current_duration >= self.runtime_rules.get(
            "max_duration_seconds", float("inf")
        )

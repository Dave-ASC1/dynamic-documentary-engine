"""
sequencer.py
------------
Dynamic Documentary Engine — Main Sequencing Engine

The core of the Dynamic Documentary Engine. Orchestrates the full
film generation process by coordinating the collection loader,
sequencing rules, and artifact selector to produce a unique ordered
sequence of artifacts on every run.

All sequencing logic is creative code — no external AI engines are used.
Selection decisions are driven entirely by metadata rules, pacing arc,
mood transition logic, and weighted random selection.

Inspired by the Brain One engine built by Brendan Dawes for the
Eno documentary (2024) — a system that produces an algorithmically
different cut of the film at every screening.

Usage:
    from engine.sequencer import Sequencer

    sequencer = Sequencer("metadata/ww2_collection_index.json")
    film = sequencer.generate(target_duration=1800)
    print(film)

Author: Oluwafemisola (David)
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.1.0
"""

from engine.collection_loader import CollectionLoader
from engine.rules import SequencingRules
from engine.artifact_selector import ArtifactSelector


class Sequencer:
    """
    The main sequencing engine for the Dynamic Documentary Engine.

    Coordinates the full film generation pipeline:
        1. Loads a collection index from disk
        2. Accepts a target runtime in seconds (4-digit max: 0001–9999)
        3. Always opens the film with the designated opening artifact
        4. Selects body artifacts using rules, pacing arc, and mood transitions
        5. Enforces B-roll + X-roll pairing — B-roll is never placed alone
        6. Always closes the film with the designated closing artifact
        7. Returns the complete ordered film sequence

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

    def __init__(self, collection_path):
        """
        Initializes the Sequencer with a path to a collection index.

        Args:
            collection_path (str): Path to the collection index JSON file.

        Raises:
            FileNotFoundError: If the collection index file does not exist.
            ValueError: If the collection index is missing required fields.
        """
        self.collection_path = collection_path

        self.loader = CollectionLoader(collection_path)
        self.collection = self.loader.load()

        runtime_rules = self.loader.get_runtime_rules()
        self.rules = SequencingRules(runtime_rules)
        self.selector = ArtifactSelector(self.rules)

    def generate(self, target_duration=None):
        """
        Generates a unique ordered film sequence from the loaded collection.

        The sequence always begins with the designated opening artifact and
        ends with the designated closing artifact. Body artifacts are selected
        in between using pacing arc, mood transitions, and weighted random
        selection until the target duration is reached.

        B-roll artifacts are always paired with an X-roll artifact immediately
        following them to provide an audio layer. A-roll artifacts stand alone.

        Args:
            target_duration (int, optional): Desired film runtime in seconds.
                                             Must be between 1 and 9999.
                                             Supports short-form and feature-length films.
                                             If not provided, uses the collection's
                                             max_duration_seconds runtime rule.

        Returns:
            list: An ordered list of artifact ID strings representing the
                  generated film sequence. B-roll entries are paired tuples:
                  ('broll_id', 'xroll_id'). A-roll entries are plain strings.
                  Example:
                  ['ww2_av_001', ('ww2_broll_002', 'ww2_xroll_003'), 'ww2_av_002']

        Raises:
            ValueError: If target_duration is outside the 1–9999 second range.
            RuntimeError: If the collection has no body artifacts to select from.
        """
        # Validate target duration is within the 4-digit range
        if target_duration is not None:
            if not (self.MIN_DURATION <= target_duration <= self.MAX_DURATION):
                raise ValueError(
                    f"target_duration must be between {self.MIN_DURATION} and "
                    f"{self.MAX_DURATION} seconds. Got: {target_duration}"
                )
            # Override the collection's max duration with the requested target
            self.rules.runtime_rules["max_duration_seconds"] = target_duration

        self.rules.reset()
        sequence = []

        # Step 1 — Always open with the designated opening artifact
        opening_id = self.loader.get_opening_artifact_id()
        opening_artifact = self._find_artifact_by_id(opening_id)

        if opening_artifact:
            sequence.append(opening_id)
            self.rules.register_selection(opening_artifact)

        # Step 2 — Select body artifacts until target duration is reached
        body_artifacts = self.loader.get_body_artifacts()

        if not body_artifacts:
            raise RuntimeError(
                "Collection has no body artifacts available for selection."
            )

        current_mood = opening_artifact.get("mood") if opening_artifact else None

        while not self.rules.has_reached_maximum_duration():

            target_pacing = self.rules.get_target_pacing()

            selected = self.selector.select_next(
                body_artifacts,
                current_mood=current_mood,
                target_pacing=target_pacing
            )

            if selected is None:
                break

            artifact_type = selected.get("artifact_type")

            if artifact_type == "B-roll":
                # B-roll must always be paired with an X-roll for audio.
                # Select an X-roll to layer over this B-roll clip.
                x_roll_artifacts = [
                    a for a in body_artifacts if a.get("artifact_type") == "X-roll"
                ]
                x_roll = self.selector.select_next(x_roll_artifacts)

                if x_roll:
                    # Store as a paired tuple — assembler will overlay these
                    sequence.append((selected.get("artifact_id"), x_roll.get("artifact_id")))
                else:
                    # No X-roll available — skip this B-roll to avoid silent video
                    continue
            else:
                # A-roll stands alone — has its own synchronized audio
                sequence.append(selected.get("artifact_id"))

            current_mood = selected.get("mood")

        # Step 3 — Always close with the designated closing artifact
        closing_id = self.loader.get_closing_artifact_id()
        closing_artifact = self._find_artifact_by_id(closing_id)

        if closing_artifact:
            sequence.append(closing_id)

        return sequence

    def _find_artifact_by_id(self, artifact_id):
        """
        Finds and returns an artifact from the collection by its ID.

        Args:
            artifact_id (str): The artifact ID to search for.

        Returns:
            dict: The artifact dictionary if found, or None if not found.
        """
        for artifact in self.loader.get_artifacts():
            if artifact.get("artifact_id") == artifact_id:
                return artifact
        return None

    def generate_multiple(self, count, target_duration=None):
        """
        Generates multiple unique film sequences from the same collection.

        Each sequence is generated independently with no shared state,
        ensuring every film is unique.

        Args:
            count (int): The number of film sequences to generate.
            target_duration (int, optional): Desired runtime per film in seconds.
                                             Must be between 1 and 9999.

        Returns:
            list: A list of film sequences.
        """
        return [self.generate(target_duration) for _ in range(count)]

"""
sequencer.py
------------
Dynamic Documentary Engine — Main Sequencing Engine

The core of the Dynamic Documentary Engine. Orchestrates the full
film generation process by coordinating the collection loader,
sequencing rules, and artifact selector to produce a unique ordered
sequence of artifacts on every run.

Inspired by the Brain One engine built by Brendan Dawes for the
Eno documentary (2024) — a system that produces an algorithmically
different cut of the film at every screening.

Usage:
    from engine.sequencer import Sequencer

    sequencer = Sequencer("metadata/ww2_collection_index.json")
    film = sequencer.generate(target_duration=600)
    print(film)

Author: Oluwafemisola David Ademoye
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

from engine.collection_loader import CollectionLoader
from engine.rules import SequencingRules
from engine.artifact_selector import ArtifactSelector


class Sequencer:
    """
    The main sequencing engine for the Dynamic Documentary Engine.

    Coordinates the full film generation pipeline:
        1. Loads a collection index from disk
        2. Initializes sequencing rules from the collection's runtime rules
        3. Always opens the film with the designated opening artifact
        4. Selects body artifacts using rules and weighted selection
        5. Always closes the film with the designated closing artifact
        6. Returns the complete ordered film sequence

    Each call to generate() produces a unique film sequence. No two
    generated films are guaranteed to be identical.

    Attributes:
        collection_path (str): Path to the collection index JSON file.
        loader (CollectionLoader): The collection loader instance.
        collection (dict): The loaded collection data.
        rules (SequencingRules): The active sequencing rules.
        selector (ArtifactSelector): The artifact selector instance.
    """

    def __init__(self, collection_path):
        """
        Initializes the Sequencer with a path to a collection index.

        Loads the collection from disk and sets up the rules engine
        and artifact selector ready for film generation.

        Args:
            collection_path (str): Path to the collection index JSON file.

        Raises:
            FileNotFoundError: If the collection index file does not exist.
            ValueError: If the collection index is missing required fields.
        """
        self.collection_path = collection_path

        # Load the collection from disk
        self.loader = CollectionLoader(collection_path)
        self.collection = self.loader.load()

        # Initialize the rules engine with the collection's runtime rules
        runtime_rules = self.loader.get_runtime_rules()
        self.rules = SequencingRules(runtime_rules)

        # Initialize the artifact selector with the rules engine
        self.selector = ArtifactSelector(self.rules)

    def generate(self, target_duration=None):
        """
        Generates a unique ordered film sequence from the loaded collection.

        The sequence always begins with the collection's designated opening
        artifact and ends with the designated closing artifact. Body artifacts
        are selected in between using the sequencing rules and weighted
        random selection until the target duration is reached.

        Args:
            target_duration (int, optional): Desired film runtime in seconds.
                                             If not provided, uses the collection's
                                             max_duration_seconds runtime rule.

        Returns:
            list: An ordered list of artifact ID strings representing the
                  generated film sequence. Example:
                  ['ww2_av_001', 'ww2_xroll_003', 'ww2_broll_002', 'ww2_av_002']

        Raises:
            RuntimeError: If the collection has no body artifacts to select from.
        """
        # Reset the rules engine state for a fresh generation session
        self.rules.reset()

        # Build the film sequence starting with an empty list
        sequence = []

        # Step 1 — Always open with the designated opening artifact
        opening_id = self.loader.get_opening_artifact_id()
        opening_artifact = self._find_artifact_by_id(opening_id)

        if opening_artifact:
            sequence.append(opening_id)
            self.rules.register_selection(opening_artifact)

        # Step 2 — Select body artifacts until the target duration is reached
        body_artifacts = self.loader.get_body_artifacts()

        if not body_artifacts:
            raise RuntimeError(
                "Collection has no body artifacts available for selection."
            )

        current_mood = opening_artifact.get("mood") if opening_artifact else None

        # Keep selecting artifacts until we hit the duration limit or run out
        while not self.rules.has_reached_maximum_duration():

            # Get the target pacing for the current position in the film arc
            target_pacing = self.rules.get_target_pacing()

            selected = self.selector.select_next(
                body_artifacts,
                current_mood=current_mood,
                target_pacing=target_pacing
            )

            # If no eligible artifacts remain, stop selection
            if selected is None:
                break

            sequence.append(selected.get("artifact_id"))

            # Update the current mood for the next selection pass
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
        all_artifacts = self.loader.get_artifacts()

        for artifact in all_artifacts:
            if artifact.get("artifact_id") == artifact_id:
                return artifact

        return None

    def generate_multiple(self, count, target_duration=None):
        """
        Generates multiple unique film sequences from the same collection.

        Each sequence is generated independently — no state is shared
        between runs, ensuring each film is unique.

        Args:
            count (int): The number of film sequences to generate.
            target_duration (int, optional): Desired runtime per film in seconds.

        Returns:
            list: A list of film sequences, where each sequence is an ordered
                  list of artifact ID strings.
        """
        films = []

        for i in range(count):
            film = self.generate(target_duration)
            films.append(film)

        return films

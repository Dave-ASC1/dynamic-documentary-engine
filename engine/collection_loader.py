"""
collection_loader.py
--------------------
Dynamic Documentary Engine — Collection Loader

Responsible for loading, validating, and parsing a collection index
from its JSON file into a structured Python object ready for use
by the sequencing engine.

A collection is the full set of media artifacts for a given project
(e.g. a WW2 documentary collection). Each collection has a master
index file that aggregates all artifacts and defines runtime rules.

Author: Oluwafemisola David Ademoye
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import json
import os


class CollectionLoader:
    """
    Loads and validates a collection index from a JSON file.

    A collection index contains:
        - Collection-level metadata (id, name, description)
        - Runtime rules (min/max duration, opening/closing artifacts)
        - A summary index of all artifacts in the collection

    Attributes:
        collection_path (str): Path to the collection index JSON file.
        collection (dict): The loaded and validated collection data.
    """

    def __init__(self, collection_path):
        """
        Initializes the CollectionLoader with the path to a collection index.

        Args:
            collection_path (str): Path to the collection index JSON file.

        Raises:
            FileNotFoundError: If the collection index file does not exist.
            ValueError: If the collection index is missing required fields.
        """
        self.collection_path = collection_path
        self.collection = None

    def load(self):
        """
        Loads the collection index from disk and validates its structure.

        Returns:
            dict: The loaded and validated collection data.

        Raises:
            FileNotFoundError: If the collection index file does not exist.
            ValueError: If the collection index is missing required fields.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        if not os.path.exists(self.collection_path):
            raise FileNotFoundError(
                f"Collection index not found at: {self.collection_path}"
            )

        with open(self.collection_path, "r") as f:
            data = json.load(f)

        self._validate(data)
        self.collection = data
        return self.collection

    def _validate(self, data):
        """
        Validates that a collection index contains all required fields.

        Args:
            data (dict): The raw collection data loaded from JSON.

        Raises:
            ValueError: If any required field is missing from the collection.
        """
        required_fields = [
            "collection_id",
            "collection_name",
            "created_at",
            "runtime_rules",
            "artifacts"
        ]

        for field in required_fields:
            if field not in data:
                raise ValueError(
                    f"Collection index is missing required field: '{field}'"
                )

        required_runtime_rules = [
            "min_duration_seconds",
            "max_duration_seconds",
            "opening_artifact_id",
            "closing_artifact_id"
        ]

        for rule in required_runtime_rules:
            if rule not in data["runtime_rules"]:
                raise ValueError(
                    f"Collection runtime_rules is missing required field: '{rule}'"
                )

    def get_artifacts(self):
        """Returns all artifacts in the loaded collection."""
        if self.collection is None:
            raise RuntimeError("Collection has not been loaded. Call load() first.")
        return self.collection.get("artifacts", [])

    def get_runtime_rules(self):
        """Returns the runtime rules for the loaded collection."""
        if self.collection is None:
            raise RuntimeError("Collection has not been loaded. Call load() first.")
        return self.collection.get("runtime_rules", {})

    def get_opening_artifact_id(self):
        """Returns the artifact ID designated as the opening of every generated film."""
        return self.get_runtime_rules().get("opening_artifact_id")

    def get_closing_artifact_id(self):
        """Returns the artifact ID designated as the closing of every generated film."""
        return self.get_runtime_rules().get("closing_artifact_id")

    def get_body_artifacts(self):
        """
        Returns only body artifacts — those available for selection
        by the sequencing engine. Excludes opening and closing artifacts.

        Returns:
            list: Artifact dictionaries with role == 'body'.
        """
        return [a for a in self.get_artifacts() if a.get("role") == "body"]

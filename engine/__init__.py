"""
__init__.py
-----------
Dynamic Documentary Engine — Engine Package

Exposes the primary public interface of the engine package.
Import the Sequencer class directly from this package to generate films.

Usage:
    from engine import Sequencer

    sequencer = Sequencer("metadata/ww2_collection_index.json")
    film = sequencer.generate(target_duration=600)
    print(film)

Author: Oluwafemisola (David)
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

from engine.sequencer import Sequencer
from engine.collection_loader import CollectionLoader
from engine.rules import SequencingRules
from engine.artifact_selector import ArtifactSelector

__all__ = [
    "Sequencer",
    "CollectionLoader",
    "SequencingRules",
    "ArtifactSelector",
]

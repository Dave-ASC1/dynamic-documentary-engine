
"""
__init__.py
-----------
Dynamic Documentary Engine — Engine Package
 
Exposes the primary public interface of the engine package.
All sequencing logic is creative code — no external AI engines are used.
Import the Sequencer and Assembler classes directly from this package
to generate and render films.
 
Usage:
    from engine import Sequencer, Assembler
 
    sequencer = Sequencer("metadata/ww2_collection_index.json")
    sequence  = sequencer.generate(target_duration=600)
 
    assembler = Assembler(
        loader=sequencer.loader,
        assets_path="/Volumes/MyDrive/dde-assets/",
        films_path="/Volumes/MyDrive/dde-films/",
    )
    film_path = assembler.render(sequence)
    print(f"Film rendered: {film_path}")
 
Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 2.0.0
"""
 
from engine.sequencer import Sequencer
from engine.assembler import Assembler
from engine.collection_loader import CollectionLoader
from engine.rules import SequencingRules
from engine.artifact_selector import ArtifactSelector
 
__all__ = [
    "Sequencer",
    "Assembler",
    "CollectionLoader",
    "SequencingRules",
    "ArtifactSelector",
]

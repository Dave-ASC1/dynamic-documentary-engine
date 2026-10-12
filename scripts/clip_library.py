"""
clip_library.py
---------------
Dynamic Documentary Engine — Clip Library (metadata editing)

Backs the Clip library page (web/frontend/library.html): lists every clip in
a collection with its labels, and saves a label the moment someone edits it,
so nobody has to open a collection index file by hand.

A save is checked against what the engine can use (a date it can read, a
pacing it knows), applied under the same lock the media sync uses, written
atomically, and the previous version of the index is kept as a backup. The
next generated film uses the new labels — nothing to restart.

Editable labels and where they matter:

    title, weight, notes           — basics (notes are for people only)
    people, geography (place)      — matched by cues
    mood, pacing, tags, theme,
    dominant_lines                 — contrast scoring between cuts
    context.date/.season/.weather  — memory triggers

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import glob
import json
import os
import shutil
from datetime import datetime, timezone

import dde_runtime
from engine.context import SEASONS, WEATHER_TERMS, normalize_date_input

PACING = ("slow", "medium", "fast")
LINES = ("horizontal", "vertical", "diagonal", "curved", "mixed")

# How many earlier versions of each collection index to keep.
BACKUPS_KEPT = 30
BACKUP_DIRNAME = ".backups"

# field -> (kind, options). Kinds: text, list, enum, weight, date.
FIELDS = {
    "title":            ("text", {"max": 200}),
    "weight":           ("weight", {}),
    "notes":            ("text", {"max": 2000}),
    "people":           ("list", {}),
    "geography":        ("text", {"max": 120}),
    "mood":             ("text", {"max": 60}),
    "pacing":           ("enum", {"choices": PACING}),
    "tags":             ("list", {}),
    "theme":            ("list", {}),
    "dominant_lines":   ("enum", {"choices": LINES}),
    "context.date":     ("date", {}),
    "context.season":   ("enum", {"choices": SEASONS}),
    "context.weather":  ("list", {}),
}

# Fields offered as type-ahead suggestions, drawn from the whole collection.
SUGGESTED = ("mood", "tags", "theme", "people", "geography", "context.weather")


class ValidationError(ValueError):
    """One or more fields failed validation.

    Attributes:
        errors (dict): field -> plain-language message.
    """

    def __init__(self, errors):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _clean_value(field, raw):
    """Checks and normalizes one field's typed value.

    Args:
        field (str): A key of FIELDS.
        raw: The value as sent by the page (string, list or number).

    Returns:
        The value to store, or None to remove the label.

    Raises:
        ValueError: With a message to show next to the field.
    """
    kind, opts = FIELDS[field]
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if field == "title":
            raise ValueError("A clip needs a title.")
        return None

    if kind == "text":
        value = " ".join(str(raw).split()) if field != "notes" else str(raw).strip()
        if len(value) > opts["max"]:
            raise ValueError(f"Keep it under {opts['max']} characters.")
        return value

    if kind == "list":
        items = raw if isinstance(raw, list) else str(raw).split(",")
        values, seen = [], set()
        for item in items:
            item = " ".join(str(item).split())
            if item and item.lower() not in seen:
                seen.add(item.lower())
                values.append(item)
        if any(len(v) > 80 for v in values):
            raise ValueError("Each item must be under 80 characters.")
        return values or None

    if kind == "enum":
        value = str(raw).strip().lower()
        if value not in opts["choices"]:
            raise ValueError(f"Choose one of: {', '.join(opts['choices'])}.")
        return value

    if kind == "weight":
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError("Must be a number.") from None
        if not 0.05 <= value <= 1:
            raise ValueError("Must be between 0.05 and 1.")
        return round(value, 2)

    if kind == "date":
        return normalize_date_input(raw)

    raise ValueError("Unknown field.")


def validate_changes(changes):
    """Validates a set of edits from the page.

    Args:
        changes (dict): field -> typed value.

    Returns:
        dict: field -> cleaned value (None = remove).

    Raises:
        ValidationError: If any field is unknown or invalid.
    """
    if not isinstance(changes, dict) or not changes:
        raise ValidationError({"_": "Nothing to save."})
    cleaned, errors = {}, {}
    for field, raw in changes.items():
        if field not in FIELDS:
            errors[field] = "This label can't be edited here."
            continue
        try:
            cleaned[field] = _clean_value(field, raw)
        except ValueError as e:
            errors[field] = str(e)
    if errors:
        raise ValidationError(errors)
    return cleaned


def _get(entry, field):
    if field.startswith("context."):
        return (entry.get("context") or {}).get(field.split(".", 1)[1])
    return entry.get(field)


def _set(entry, field, value):
    if field.startswith("context."):
        key = field.split(".", 1)[1]
        context = dict(entry.get("context") or {})
        if value is None:
            context.pop(key, None)
        else:
            context[key] = value
        if context:
            entry["context"] = context
        else:
            entry.pop("context", None)
    elif value is None:
        entry.pop(field, None)
    else:
        entry[field] = value


def is_labelled(entry):
    """True once a person has added anything beyond what auto-detection
    fills in (length, a pacing guess, a colour tag, a filename title)."""
    if any(entry.get(k) for k in ("mood", "theme", "people", "geography", "notes",
                                  "dominant_lines", "context")):
        return True
    return any(not str(t).startswith("color-") for t in entry.get("tags") or [])


def clip_view(entry):
    """The page's view of one index entry."""
    return {
        "artifact_id": entry.get("artifact_id"),
        "artifact_type": entry.get("artifact_type"),
        "filename": entry.get("filename"),
        "duration_seconds": entry.get("duration_seconds"),
        "labelled": is_labelled(entry),
        "fields": {field: _get(entry, field) for field in FIELDS},
    }


def list_clips(index_path):
    """Every clip in a collection index, with its editable labels and the
    collection's existing values for type-ahead suggestions.

    Args:
        index_path (str): The collection index path.

    Returns:
        dict: {"clips": [...], "suggestions": {field: [values]}}.
    """
    with dde_runtime.INDEX_LOCK:
        with open(index_path) as f:
            data = json.load(f)

    suggestions = {field: set() for field in SUGGESTED}
    for entry in data.get("artifacts", []):
        for field in SUGGESTED:
            value = _get(entry, field)
            values = value if isinstance(value, list) else [value] if value else []
            suggestions[field].update(v for v in values if not str(v).startswith("color-"))
    suggestions["context.weather"].update(WEATHER_TERMS)

    order = {"A-roll": 0, "B-roll": 1, "X-roll": 2}
    clips = sorted(
        (clip_view(e) for e in data.get("artifacts", [])),
        key=lambda c: (order.get(c["artifact_type"], 3), (c["fields"]["title"] or "").lower()),
    )
    return {
        "clips": clips,
        "suggestions": {k: sorted(v, key=str.lower) for k, v in suggestions.items()},
    }


def _backup(index_path):
    """Copies the index as it stands into .backups/<index name>/ and keeps
    only the newest BACKUPS_KEPT copies."""
    name = os.path.splitext(os.path.basename(index_path))[0]
    folder = os.path.join(os.path.dirname(index_path), BACKUP_DIRNAME, name)
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    shutil.copy2(index_path, os.path.join(folder, f"{stamp}.json"))
    for old in sorted(glob.glob(os.path.join(folder, "*.json")))[:-BACKUPS_KEPT]:
        os.remove(old)


def update_clip(index_path, artifact_id, changes):
    """Saves edited labels for one clip.

    Args:
        index_path (str):  The collection index path.
        artifact_id (str): The clip to edit.
        changes (dict):    field -> typed value; an empty value removes it.

    Returns:
        dict: The clip's updated view (see clip_view).

    Raises:
        ValidationError: If a field is unknown or invalid (nothing saved).
        KeyError: If the clip is not in the index (nothing saved).
    """
    cleaned = validate_changes(changes)
    with dde_runtime.INDEX_LOCK:
        with open(index_path) as f:
            data = json.load(f)
        entry = next(
            (a for a in data.get("artifacts", []) if a.get("artifact_id") == artifact_id),
            None,
        )
        if entry is None:
            raise KeyError(artifact_id)

        before = json.dumps(entry, sort_keys=True)
        for field, value in cleaned.items():
            _set(entry, field, value)
        if json.dumps(entry, sort_keys=True) != before:
            _backup(index_path)
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            dde_runtime.write_index(index_path, data)
        return clip_view(entry)


def options():
    """The fixed choices the page offers."""
    return {
        "pacing": list(PACING),
        "dominant_lines": list(LINES),
        "seasons": list(SEASONS),
        "weather": list(WEATHER_TERMS),
    }

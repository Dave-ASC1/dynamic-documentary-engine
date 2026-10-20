"""
clip_previews.py
----------------
Dynamic Documentary Engine — Clip Thumbnails and Previews

Makes what the Clip library shows for each video clip: a small still
picture (thumbnail) and a lightweight preview copy that plays in any
browser. Source footage can be 4K or in formats many browsers can't play
(iPhone HEVC .mov, for example), so neither is served straight from the
original file.

Both are made once, with FFmpeg, the first time they're asked for, and kept
in the topic's hidden .previews/ folder (gitignored, never packaged). Each
is keyed by the clip's file name, size and modification time, so replacing a
clip makes a fresh one. Only a couple of FFmpeg processes run at once, so a
table of many clips loading together doesn't swamp the machine.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import hashlib
import os
import subprocess
import threading

PREVIEW_DIRNAME = ".previews"

# Thumbnails fit a 320x180 box (sharp at the table's ~96px size on retina
# screens); previews fit 640x640, enough to recognise a shot, small enough
# to stream over a shared link.
THUMB_BOX = (320, 180)
PREVIEW_BOX = 640

# How far into a clip the thumbnail is taken: past any fade-in, before the end.
THUMB_POSITION = 0.3

# At most this many FFmpeg jobs at once across the whole server.
_SLOTS = threading.BoundedSemaphore(2)
# One lock per output file, so two requests never build the same one.
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


class PreviewUnavailable(Exception):
    """The clip has no picture, or FFmpeg couldn't read it."""


def _lock_for(path):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path, threading.Lock())


def _source_path(assets_path, entry):
    """The clip's file, refusing anything outside the topic's assets."""
    filename = entry.get("filename")
    if not filename:
        raise PreviewUnavailable("No file for this clip.")
    root = os.path.realpath(assets_path)
    source = os.path.realpath(os.path.join(root, filename))
    if os.path.commonpath([source, root]) != root or not os.path.isfile(source):
        raise PreviewUnavailable("Clip file not found.")
    return source


def _cache_path(assets_path, entry, source, kind, extension):
    stat = os.stat(source)
    key = hashlib.sha1(
        f"{entry.get('filename')}|{stat.st_size}|{int(stat.st_mtime)}".encode()
    ).hexdigest()[:16]
    topic_folder = os.path.dirname(os.path.normpath(assets_path))
    return os.path.join(topic_folder, PREVIEW_DIRNAME, kind, f"{key}{extension}")


def _build(output, cmd, timeout):
    """Runs one FFmpeg job into output (via a temporary file) unless it
    already exists. Returns output."""
    with _lock_for(output):
        if os.path.isfile(output):
            return output
        os.makedirs(os.path.dirname(output), exist_ok=True)
        tmp = output + ".part" + os.path.splitext(output)[1]
        error = ""
        with _SLOTS:
            try:
                proc = subprocess.run(cmd + [tmp], capture_output=True, timeout=timeout)
            except (subprocess.SubprocessError, OSError) as e:
                proc = None
                error = str(e)
        if proc is None or proc.returncode != 0 or not os.path.isfile(tmp):
            if os.path.exists(tmp):
                os.remove(tmp)
            detail = error if proc is None else proc.stderr.decode(errors="replace")[-300:]
            raise PreviewUnavailable(f"FFmpeg couldn't make it: {detail}")
        os.replace(tmp, output)
        return output


def _require_video(entry):
    if entry.get("artifact_type") == "X-roll":
        raise PreviewUnavailable("Sound-only clips have no picture.")


def thumbnail(assets_path, entry):
    """Path to the clip's thumbnail JPEG, made on first request.

    Args:
        assets_path (str): The topic's assets folder.
        entry (dict):      The clip's index entry.

    Returns:
        str: Path to the JPEG.

    Raises:
        PreviewUnavailable: Sound-only clip, missing file, or FFmpeg failure.
    """
    _require_video(entry)
    source = _source_path(assets_path, entry)
    output = _cache_path(assets_path, entry, source, "thumbs", ".jpg")
    duration = entry.get("duration_seconds") or 0
    at = max(0.0, min(duration * THUMB_POSITION, duration - 0.1)) if duration else 1.0
    w, h = THUMB_BOX
    return _build(output, [
        "ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", source,
        "-frames:v", "1",
        "-vf", f"scale=w='min({w},iw)':h='min({h},ih)':force_original_aspect_ratio=decrease",
        "-q:v", "4",
    ], timeout=60)


def preview(assets_path, entry):
    """Path to the clip's small H.264 preview MP4, made on first request.

    Args:
        assets_path (str): The topic's assets folder.
        entry (dict):      The clip's index entry.

    Returns:
        str: Path to the MP4.

    Raises:
        PreviewUnavailable: Sound-only clip, missing file, or FFmpeg failure.
    """
    _require_video(entry)
    source = _source_path(assets_path, entry)
    output = _cache_path(assets_path, entry, source, "clips", ".mp4")
    box = PREVIEW_BOX
    return _build(output, [
        "ffmpeg", "-y", "-v", "error", "-i", source,
        "-vf", (f"scale=w='min({box},iw)':h='min({box},ih)':force_original_aspect_ratio=decrease,"
                "scale=trunc(iw/2)*2:trunc(ih/2)*2"),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ac", "2",
        "-movflags", "+faststart",
    ], timeout=300)

"""
assembler.py
------------
Dynamic Documentary Engine — Film Assembler

Takes the ordered sequence produced by Sequencer.generate() and renders
it into a single playable film file using FFmpeg.

The Assembler is the final stage of the engine pipeline:

    CollectionLoader  →  loads and validates a collection index
    Sequencer         →  generates a unique ordered artifact sequence
    Assembler         →  renders that sequence into a film file

Usage:
    from engine.sequencer import Sequencer
    from engine.assembler import Assembler

    sequencer = Sequencer("metadata/ww2_collection_index.json")
    sequence  = sequencer.generate(target_duration=600)

    assembler = Assembler(
        loader=sequencer.loader,
        assets_path="/Volumes/MyDrive/dde-assets/",
        films_path="/Volumes/MyDrive/dde-films/",
        metadata_path="metadata/",
    )
    film_path = assembler.render(sequence)
    print(f"Film rendered: {film_path}")

Sequence Format:
    Sequencer.generate() returns a list of mixed types:
        - str:   A-roll artifact ID  →  stands alone (has synchronized audio+video)
        - tuple: (B-roll ID, X-roll ID)  →  video-only clip + audio-only clip paired

    The assembler handles both transparently.

Source Types:
    Each artifact declares a source_type in its individual metadata JSON:
        - "local":  A stored file on disk or an external drive.
                    Resolved as: assets_path / filename
        - "stream": A live webcam or broadcast feed (RTSP, HLS).
                    Resolved as: the stream_url from the artifact's metadata JSON.
                    FFmpeg handles live streams natively as an input source.

    Source type is read from the individual artifact JSON file (not the collection
    index summary, which does not carry stream_url). If no individual JSON exists
    for an artifact, source_type defaults to "local".

FFmpeg Requirement:
    FFmpeg must be installed and available on the system PATH.
    Install on macOS:  brew install ffmpeg
    Verify:            ffmpeg -version

Author: Oluwafemisola David Ademoye
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import json
import logging
import os
import subprocess
import tempfile
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class Assembler:
    """
    Renders a film sequence into a single playable file using FFmpeg.

    The Assembler accepts the list returned by Sequencer.generate() and
    processes each entry — A-roll strings and B-roll/X-roll tuples — into
    temporary segment files, then concatenates them in sequence order into
    the final film.

    Each call to render() produces a uniquely named output file so no two
    generated films ever overwrite each other.

    Attributes:
        loader (CollectionLoader):  The collection loader from the Sequencer.
                                    Used to look up artifact summary dicts
                                    by ID and to retrieve the collection ID
                                    for output naming.
        assets_path (str):          Base directory for local media files.
                                    Can point to an external hard drive:
                                    e.g. "/Volumes/MyDrive/dde-assets/"
        films_path (str):           Directory where rendered film files are written.
                                    Can point to an external hard drive:
                                    e.g. "/Volumes/MyDrive/dde-films/"
        metadata_path (str):        Directory containing individual artifact
                                    JSON files. Used to resolve source_type
                                    and stream_url for each artifact.
                                    Defaults to "metadata/".
        video_codec (str):          FFmpeg video codec. Default: "libx264".
        audio_codec (str):          FFmpeg audio codec. Default: "aac".
        pix_fmt (str):              FFmpeg pixel format. Default: "yuv420p".
        output_format (str):        Output container format. Default: "mp4".
    """

    # FFmpeg codec defaults — H.264 + AAC in MP4 is the most universally
    # compatible combination for documentary playback.
    DEFAULT_VIDEO_CODEC = "libx264"
    DEFAULT_AUDIO_CODEC = "aac"
    DEFAULT_PIX_FMT    = "yuv420p"
    DEFAULT_FORMAT     = "mp4"

    # Seconds to capture from a live stream per slot.
    # Overridden by the artifact's duration_seconds if present.
    DEFAULT_STREAM_CAPTURE_SECONDS = 10

    def __init__(
        self,
        loader,
        assets_path: str = "./assets/",
        films_path: str = "./films/",
        metadata_path: str = "metadata/",
        video_codec: str = DEFAULT_VIDEO_CODEC,
        audio_codec: str = DEFAULT_AUDIO_CODEC,
        pix_fmt: str = DEFAULT_PIX_FMT,
        output_format: str = DEFAULT_FORMAT,
    ):
        """
        Initializes the Assembler.

        Args:
            loader (CollectionLoader): The loader instance from the Sequencer.
                Used to look up artifact summary dicts and collection metadata.
            assets_path (str):   Base directory for local media files.
                                 Trailing slash optional — normalised internally.
            films_path (str):    Output directory for rendered film files.
                                 Created automatically if it does not exist.
            metadata_path (str): Directory containing individual artifact JSON files.
                                 Used for stream_url resolution.
            video_codec (str):   FFmpeg video codec string.
            audio_codec (str):   FFmpeg audio codec string.
            pix_fmt (str):       FFmpeg pixel format string.
            output_format (str): Output container format extension (e.g. "mp4").
        """
        self.loader        = loader
        self.assets_path   = os.path.normpath(assets_path)
        self.films_path    = os.path.normpath(films_path)
        self.metadata_path = os.path.normpath(metadata_path)
        self.video_codec   = video_codec
        self.audio_codec   = audio_codec
        self.pix_fmt       = pix_fmt
        self.output_format = output_format

    # ------------------------------------------------------------------
    # Public Interface
    # ------------------------------------------------------------------

    def render(self, sequence: list) -> str:
        """
        Renders a film sequence into a single output file.

        Iterates over the sequence list produced by Sequencer.generate(),
        renders each slot to a temporary segment file, concatenates all
        segments in order, and writes the final film to films_path.

        Slot types:
            str entry   → A-roll: render video+audio as-is.
            tuple entry → B-roll + X-roll: layer X-roll audio over B-roll video.

        Slots that fail to render (missing file, unreachable stream) are
        skipped with a logged warning rather than aborting the entire film.
        A RuntimeError is raised only if NO segments render successfully.

        Args:
            sequence (list): The ordered sequence from Sequencer.generate().
                             Contains str (A-roll IDs) and tuple (B/X-roll pairs).

        Returns:
            str: Absolute path to the rendered film file.

        Raises:
            ValueError:    If sequence is empty.
            RuntimeError:  If FFmpeg is not found on PATH, or if no segments
                           render successfully.
        """
        if not sequence:
            raise ValueError("Cannot render an empty sequence.")

        self._verify_ffmpeg()
        os.makedirs(self.films_path, exist_ok=True)

        collection_id = self.loader.collection.get("collection_id", "unknown")
        film_path = os.path.join(
            self.films_path,
            self._generate_film_filename(collection_id),
        )

        logger.info(
            "Render started | collection: %s | slots: %d | output: %s",
            collection_id,
            len(sequence),
            film_path,
        )

        segment_paths = []

        with tempfile.TemporaryDirectory() as tmpdir:

            for i, entry in enumerate(sequence):
                segment_path = os.path.join(
                    tmpdir, f"segment_{i:04d}.{self.output_format}"
                )

                try:
                    if isinstance(entry, tuple):
                        # B-roll + X-roll paired slot
                        broll_id, xroll_id = entry
                        rendered = self._render_broll_xroll_slot(
                            broll_id, xroll_id, segment_path
                        )
                    else:
                        # A-roll standalone slot
                        rendered = self._render_aroll_slot(entry, segment_path)

                    if rendered:
                        segment_paths.append(segment_path)
                        logger.info(
                            "Slot %d/%d rendered → %s",
                            i + 1, len(sequence),
                            os.path.basename(segment_path),
                        )

                except Exception as e:
                    logger.warning(
                        "Slot %d skipped — render error: %s", i + 1, e
                    )
                    continue

            if not segment_paths:
                raise RuntimeError(
                    "No segments rendered successfully. Film cannot be assembled. "
                    "Check that asset files exist and FFmpeg is installed."
                )

            # Concatenate all segments into the final film
            concat_list_path = os.path.join(tmpdir, "concat_list.txt")
            self._write_concat_list(segment_paths, concat_list_path)
            self._run_ffmpeg(
                self._build_concat_command(concat_list_path, film_path),
                label="final concat",
            )

        # tmpdir and all segments are automatically cleaned up here
        logger.info("Film rendered successfully → %s", film_path)
        return film_path

    # ------------------------------------------------------------------
    # Slot Renderers
    # ------------------------------------------------------------------

    def _render_aroll_slot(self, artifact_id: str, output_path: str) -> bool:
        """
        Renders a single A-roll artifact to a segment file.

        A-roll artifacts carry synchronized audio and video and render
        directly without any additional processing.

        Args:
            artifact_id (str): The artifact ID to render.
            output_path (str): Path for the output segment file.

        Returns:
            bool: True if the segment rendered successfully.

        Raises:
            ValueError:       If the artifact ID cannot be found in the collection.
            FileNotFoundError: If the local asset file does not exist.
            RuntimeError:     If FFmpeg fails.
        """
        artifact = self._require_artifact(artifact_id)
        source, is_stream = self._resolve_source(artifact)
        duration = artifact.get("duration_seconds")

        cmd = self._build_aroll_command(source, output_path, duration, is_stream)
        self._run_ffmpeg(cmd, label=f"A-roll {artifact_id}")
        return True

    def _render_broll_xroll_slot(
        self,
        broll_id: str,
        xroll_id: str,
        output_path: str,
    ) -> bool:
        """
        Renders a B-roll + X-roll paired slot to a segment file.

        The B-roll provides the video track. The X-roll provides the audio
        track. FFmpeg layers the X-roll audio over the B-roll video, looping
        the audio if shorter than the video and truncating at the B-roll's
        duration.

        B-roll is never rendered without audio — this is a core structural
        rule of the engine. If the X-roll source cannot be resolved, this
        method raises rather than producing a silent video segment.

        Args:
            broll_id (str):    The B-roll artifact ID (video source).
            xroll_id (str):    The X-roll artifact ID (audio source).
            output_path (str): Path for the output segment file.

        Returns:
            bool: True if the segment rendered successfully.

        Raises:
            ValueError:       If either artifact ID is not found.
            FileNotFoundError: If a local asset file does not exist.
            RuntimeError:     If FFmpeg fails.
        """
        broll = self._require_artifact(broll_id)
        xroll = self._require_artifact(xroll_id)

        broll_source, broll_is_stream = self._resolve_source(broll)
        xroll_source, xroll_is_stream = self._resolve_source(xroll)

        duration = broll.get("duration_seconds")

        cmd = self._build_broll_xroll_command(
            broll_source, xroll_source, output_path,
            duration, broll_is_stream, xroll_is_stream,
        )
        self._run_ffmpeg(cmd, label=f"B-roll {broll_id} + X-roll {xroll_id}")
        return True

    # ------------------------------------------------------------------
    # Artifact Lookup and Source Resolution
    # ------------------------------------------------------------------

    def _require_artifact(self, artifact_id: str) -> dict:
        """
        Looks up an artifact summary dict by ID from the loaded collection.

        The collection index summary dict contains: artifact_id, artifact_type,
        role, filename, duration_seconds, mood, pacing, tags. This is sufficient
        for local file resolution. For stream sources, _resolve_source() will
        load the full individual artifact JSON to retrieve stream_url.

        Args:
            artifact_id (str): The artifact ID to look up.

        Returns:
            dict: The artifact summary dictionary.

        Raises:
            ValueError: If no artifact with that ID exists in the collection.
        """
        for artifact in self.loader.get_artifacts():
            if artifact.get("artifact_id") == artifact_id:
                return artifact

        raise ValueError(
            f"Artifact '{artifact_id}' not found in collection "
            f"'{self.loader.collection.get('collection_id', 'unknown')}'. "
            f"Ensure it is listed in the collection index."
        )

    def _load_full_artifact(self, artifact_id: str) -> Optional[dict]:
        """
        Loads the full individual artifact JSON file for an artifact.

        Individual artifact JSON files contain the complete file object
        including source_type and stream_url — fields not present in the
        collection index summary. The assembler only loads the full JSON
        when it needs to check source_type or retrieve stream_url.

        Looks for the file at: metadata_path / artifact_id.json

        Args:
            artifact_id (str): The artifact ID to load.

        Returns:
            dict: The full artifact metadata dict, or None if the file
                  does not exist (treated as a local artifact).
        """
        artifact_json_path = os.path.join(
            self.metadata_path, f"{artifact_id}.json"
        )
        if not os.path.exists(artifact_json_path):
            return None

        with open(artifact_json_path, "r") as f:
            return json.load(f)

    def _resolve_source(self, artifact: dict) -> tuple:
        """
        Resolves the media source for an artifact to an FFmpeg-ready input string.

        Resolution strategy:
            1. Load the full individual artifact JSON to check source_type.
            2. If source_type is "stream": return the stream_url directly.
               FFmpeg accepts RTSP and HLS URLs as -i inputs natively.
            3. If source_type is "local" (or no JSON exists): resolve the
               file path as assets_path / filename.
               'filename' comes from the collection index summary dict,
               which always has it at the top level.

        Args:
            artifact (dict): The artifact summary dict from the collection index.

        Returns:
            tuple: (source_string, is_stream)
                source_string (str):  FFmpeg-compatible input (path or URL).
                is_stream (bool):     True if this is a live stream source.

        Raises:
            ValueError:       If source_type is "stream" but no stream_url is found.
            FileNotFoundError: If source_type is "local" but the file does not exist.
        """
        artifact_id = artifact.get("artifact_id")
        full_artifact = self._load_full_artifact(artifact_id)

        # Determine source_type — defaults to "local" if no individual JSON exists
        source_type = "local"
        if full_artifact:
            source_type = full_artifact.get("file", {}).get("source_type", "local")

        if source_type == "stream":
            stream_url = full_artifact.get("file", {}).get("stream_url")
            if not stream_url:
                raise ValueError(
                    f"Artifact '{artifact_id}' has source_type 'stream' but "
                    f"no stream_url is defined in its metadata JSON."
                )
            logger.debug("Resolved stream source for %s: %s", artifact_id, stream_url)
            return stream_url, True

        # Local file — resolve from summary dict's 'filename' field
        filename = artifact.get("filename")
        if not filename:
            raise ValueError(
                f"Artifact '{artifact_id}' has no filename in the collection index. "
                f"Ensure the collection index entry includes a 'filename' field."
            )

        full_path = os.path.join(self.assets_path, filename)
        if not os.path.exists(full_path):
            raise FileNotFoundError(
                f"Asset file not found: {full_path}\n"
                f"Check that assets_path is correct and the file has been added "
                f"to the assets directory. artifact_id: '{artifact_id}'"
            )

        logger.debug("Resolved local source for %s: %s", artifact_id, full_path)
        return full_path, False

    # ------------------------------------------------------------------
    # FFmpeg Command Builders
    # ------------------------------------------------------------------

    def _build_aroll_command(
        self,
        source: str,
        output_path: str,
        duration: Optional[float],
        is_stream: bool,
    ) -> list:
        """
        Builds the FFmpeg command to render an A-roll clip to a segment file.

        A-roll artifacts have synchronized audio and video and render
        directly. For live stream sources, a capture duration is applied
        before the input so FFmpeg stops reading after the specified seconds.

        Args:
            source:      FFmpeg-compatible input string (file path or stream URL).
            output_path: Path for the rendered output segment file.
            duration:    Duration in seconds to render. If None, renders the
                         full clip (local) or uses DEFAULT_STREAM_CAPTURE_SECONDS
                         (stream).
            is_stream:   True if source is a live stream.

        Returns:
            list: FFmpeg command as a list of argument strings.
        """
        cmd = ["ffmpeg", "-y"]  # -y: overwrite output without prompting

        if is_stream:
            capture = duration if duration else self.DEFAULT_STREAM_CAPTURE_SECONDS
            # For streams, -t before -i limits how long FFmpeg reads the input
            cmd += ["-t", str(capture)]

        cmd += ["-i", source]

        # For local files, -t after -i trims the clip to the specified duration
        if duration and not is_stream:
            cmd += ["-t", str(duration)]

        cmd += [
            "-vcodec", self.video_codec,
            "-acodec", self.audio_codec,
            "-pix_fmt", self.pix_fmt,
            output_path,
        ]

        return cmd

    def _build_broll_xroll_command(
        self,
        video_source: str,
        audio_source: str,
        output_path: str,
        duration: Optional[float],
        video_is_stream: bool,
        audio_is_stream: bool,
    ) -> list:
        """
        Builds the FFmpeg command to layer X-roll audio over B-roll video.

        B-roll is video-only (no audio track). X-roll is audio-only. This
        command takes both as inputs and combines them:
            - Video track: taken from input 0 (B-roll), via -map 0:v
            - Audio track: taken from input 1 (X-roll), via -map 1:a
            - -stream_loop -1: loops the X-roll audio indefinitely so it
              always covers the full B-roll duration regardless of length.
            - -shortest: stops encoding at whichever input ends first —
              in practice this is always the B-roll video, ensuring the
              output duration exactly matches the B-roll clip length.

        Args:
            video_source:     FFmpeg input string for the B-roll video.
            audio_source:     FFmpeg input string for the X-roll audio.
            output_path:      Path for the rendered output segment file.
            duration:         Duration in seconds (applied to B-roll length).
            video_is_stream:  True if video source is a live stream.
            audio_is_stream:  True if audio source is a live stream.

        Returns:
            list: FFmpeg command as a list of argument strings.
        """
        cmd = ["ffmpeg", "-y"]

        # B-roll video input
        if video_is_stream:
            capture = duration if duration else self.DEFAULT_STREAM_CAPTURE_SECONDS
            cmd += ["-t", str(capture)]
        cmd += ["-i", video_source]

        # X-roll audio input — loop indefinitely so it always covers the video
        if audio_is_stream:
            cmd += ["-t", str(duration if duration else self.DEFAULT_STREAM_CAPTURE_SECONDS)]
        cmd += ["-stream_loop", "-1", "-i", audio_source]

        # Trim to B-roll duration for local video (stream already limited above)
        if duration and not video_is_stream:
            cmd += ["-t", str(duration)]

        cmd += [
            "-map", "0:v",      # Video from input 0 (B-roll)
            "-map", "1:a",      # Audio from input 1 (X-roll)
            "-shortest",         # Stop at end of B-roll video
            "-vcodec", self.video_codec,
            "-acodec", self.audio_codec,
            "-pix_fmt", self.pix_fmt,
            output_path,
        ]

        return cmd

    def _build_concat_command(
        self, concat_list_path: str, output_path: str
    ) -> list:
        """
        Builds the FFmpeg command to concatenate all segment files into the
        final film using the concat demuxer.

        The concat demuxer (-f concat) joins segment files in the order listed
        in the concat list file. Re-encoding is applied to ensure consistent
        codec output across all segments regardless of source variation.

        Args:
            concat_list_path: Path to the FFmpeg concat list text file.
            output_path:      Path for the final film output file.

        Returns:
            list: FFmpeg command as a list of argument strings.
        """
        return [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",       # Allow absolute paths in the concat list
            "-i", concat_list_path,
            "-vcodec", self.video_codec,
            "-acodec", self.audio_codec,
            "-pix_fmt", self.pix_fmt,
            output_path,
        ]

    # ------------------------------------------------------------------
    # Concat List Writer
    # ------------------------------------------------------------------

    def _write_concat_list(self, segment_paths: list, output_path: str) -> None:
        """
        Writes an FFmpeg concat demuxer list file from a list of segment paths.

        Format:
            file '/absolute/path/to/segment_0000.mp4'
            file '/absolute/path/to/segment_0001.mp4'
            ...

        Absolute paths are used so the concat command works regardless of
        the working directory at render time.

        Args:
            segment_paths: Ordered list of absolute paths to segment files.
            output_path:   Path to write the concat list file.
        """
        with open(output_path, "w") as f:
            for path in segment_paths:
                f.write(f"file '{os.path.abspath(path)}'\n")

        logger.debug(
            "Wrote concat list with %d segments → %s",
            len(segment_paths), output_path,
        )

    # ------------------------------------------------------------------
    # FFmpeg Runner
    # ------------------------------------------------------------------

    def _run_ffmpeg(self, cmd: list, label: str = "") -> None:
        """
        Executes an FFmpeg command as a subprocess.

        Captures stdout and stderr so FFmpeg's verbose output does not
        flood the terminal. Logs stderr at DEBUG level for diagnostics.
        Raises RuntimeError on non-zero exit so the caller can handle
        individual slot failures without crashing the whole render.

        Args:
            cmd:   The FFmpeg command as a list of strings.
            label: Human-readable label for log messages.

        Raises:
            RuntimeError: If FFmpeg exits with a non-zero return code.
        """
        label_str = f" [{label}]" if label else ""
        logger.info("FFmpeg%s: %s", label_str, " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.debug("FFmpeg stderr:\n%s", result.stderr)
            raise RuntimeError(
                f"FFmpeg failed{label_str} (exit code {result.returncode}).\n"
                f"Command: {' '.join(cmd)}\n"
                f"Stderr: {result.stderr[-500:]}"  # Last 500 chars to keep it readable
            )

        logger.info("FFmpeg completed%s.", label_str)

    # ------------------------------------------------------------------
    # FFmpeg Availability Check
    # ------------------------------------------------------------------

    def _verify_ffmpeg(self) -> None:
        """
        Verifies that FFmpeg is installed and available on the system PATH.

        Called once at the start of render() before any processing begins,
        so the error is immediate and clear rather than appearing mid-render.

        Raises:
            RuntimeError: If FFmpeg is not found on PATH.
        """
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "FFmpeg is not installed or not available on your PATH.\n"
                "Install on macOS: brew install ffmpeg\n"
                "Verify with:      ffmpeg -version"
            )

    # ------------------------------------------------------------------
    # Film Naming
    # ------------------------------------------------------------------

    def _generate_film_filename(self, collection_id: str) -> str:
        """
        Generates a unique filename for a rendered film.

        Format: film_<collection_id>_<YYYYMMDD_HHMMSS>_<short_uuid>.<format>
        Example: film_ww2_20260622_143201_a3f9.mp4

        The timestamp + short UUID combination ensures no two rendered films
        ever share a filename, even if generated within the same second.

        Args:
            collection_id (str): The collection identifier for the film.

        Returns:
            str: A unique filename string.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid.uuid4())[:4]
        safe_collection_id = collection_id.replace(" ", "_").lower()
        return f"film_{safe_collection_id}_{timestamp}_{short_uuid}.{self.output_format}"

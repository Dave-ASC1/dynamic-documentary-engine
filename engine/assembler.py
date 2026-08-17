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
import math
import os
import random
import subprocess
import tempfile
from typing import Optional

from engine.cancellation import GenerationCancelled, run_subprocess

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
    DEFAULT_OUTPUT_WIDTH = 1280
    DEFAULT_OUTPUT_HEIGHT = 720
    DEFAULT_OUTPUT_FPS = 30
    DEFAULT_VIDEO_PRESET = "veryfast"

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
        output_width: int = DEFAULT_OUTPUT_WIDTH,
        output_height: int = DEFAULT_OUTPUT_HEIGHT,
        output_fps: int = DEFAULT_OUTPUT_FPS,
        video_preset: str = DEFAULT_VIDEO_PRESET,
        cancel_token=None,
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
            output_width (int):  Normalized segment width in pixels.
            output_height (int): Normalized segment height in pixels.
            output_fps (int):    Normalized segment frame rate.
            video_preset (str):  FFmpeg encoder preset for segment rendering.
            cancel_token:        Optional CancellationToken. When supplied,
                                 the render loop stops between slots if
                                 cancelled and the running FFmpeg process is
                                 terminated. None means not cancellable.
        """
        self.loader        = loader
        self.assets_path   = os.path.normpath(assets_path)
        self.films_path    = os.path.normpath(films_path)
        self.metadata_path = os.path.normpath(metadata_path)
        self.video_codec   = video_codec
        self.audio_codec   = audio_codec
        self.pix_fmt       = pix_fmt
        self.output_format = output_format
        self.output_width  = output_width
        self.output_height = output_height
        self.output_fps    = output_fps
        self.video_preset  = video_preset
        self.cancel_token  = cancel_token

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
                # Stop between slots on cancel — the FFmpeg call for the
                # slot already in flight is killed by the token itself.
                if self.cancel_token is not None:
                    self.cancel_token.raise_if_cancelled()

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

                except GenerationCancelled:
                    # A deliberate stop, not a bad slot — must escape the
                    # per-slot "skip and keep going" handler below.
                    raise

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
            self._run_ffmpeg(
                self._build_concat_command(segment_paths, film_path),
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

        # Every segment must carry an audio stream for the concat filter's
        # graph to be valid. An A-roll whose file happens to have no audio
        # gets a silent one rather than being left without.
        has_audio = is_stream or self._has_audio_stream(source)

        cmd = self._build_aroll_command(
            source, output_path, duration, is_stream, has_audio
        )
        self._run_ffmpeg(cmd, label=f"A-roll {artifact_id}")
        return True

    def _has_audio_stream(self, source: str) -> bool:
        """True if the media file carries at least one audio stream."""
        try:
            probe = run_subprocess(
                ["ffprobe", "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=index", "-of", "csv=p=0", source],
                self.cancel_token, capture_output=True, text=True, timeout=30,
            )
        except GenerationCancelled:
            raise
        except (subprocess.SubprocessError, OSError):
            # Can't tell — assume none and let the silent track be added,
            # which is safe either way.
            return False
        return bool(probe.stdout.strip())

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

        When the X-roll's own duration is longer than the B-roll clip it's
        paired with, only a slice of it will ever be heard. To avoid always
        playing the same opening slice of a long audio file, a random start
        offset within the X-roll is picked each render (see
        _pick_xroll_start_offset), so different pairings surface different
        parts of the same file.

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

        excerpts, crossfade = self._plan_xroll_excerpts(
            xroll.get("duration_seconds"), duration, xroll_is_stream
        )

        cmd = self._build_broll_xroll_command(
            broll_source, xroll_source, output_path,
            duration, broll_is_stream, xroll_is_stream,
            excerpts, crossfade,
        )
        self._run_ffmpeg(cmd, label=f"B-roll {broll_id} + X-roll {xroll_id}")
        return True

    # Crossfade applied where one excerpt hands over to the next. Long
    # enough to hide the seam, short enough not to audibly dip the level.
    MAX_EXCERPT_CROSSFADE_SECONDS = 0.4

    # Fraction of a short audio file used per excerpt. Below 1.0 so there
    # is room left over for the start offset to actually vary — at 1.0
    # every excerpt would be forced to start at 0 and be identical.
    EXCERPT_COVERAGE = 0.8

    # Ceiling on excerpts per slot, so a very short audio file under a long
    # clip can't build an unreasonable filter graph.
    MAX_EXCERPTS = 24

    # Extra audio built beyond the clip length. acrossfade consumes a little
    # more than the nominal overlap, so planning for exactly the clip length
    # leaves the bed fractionally short — and since -shortest ends the
    # segment at whichever stream runs out first, that would cut the video
    # early. The surplus is discarded by -shortest as intended.
    EXCERPT_SURPLUS_SECONDS = 1.0

    def _plan_xroll_excerpts(
        self,
        xroll_duration: Optional[float],
        broll_duration: Optional[float],
        xroll_is_stream: bool,
    ):
        """
        Plans which parts of an X-roll are heard under a B-roll clip.

        Audio files are never required to match clip lengths. What happens
        depends on how the two compare:

        - **Audio at least as long as the clip** — one continuous excerpt
          from a random start offset. A two-minute file under a ten-second
          clip surfaces a different ten seconds every time it's used,
          rather than always its opening seconds.

        - **Audio shorter than the clip** — several excerpts, each from its
          own random offset, handed over with a short crossfade. Previously
          this looped the file from the same point, and the restart was
          audible as the sound changing with no cut on screen. Jumping to a
          different excerpt instead keeps the bed continuous, never repeats
          within the slot, and needs no restriction on which audio can pair
          with which clip.

        Args:
            xroll_duration (float): The X-roll's own length in seconds.
            broll_duration (float): The paired B-roll's length in seconds.
            xroll_is_stream (bool): True if the X-roll is a live stream.

        Returns:
            tuple: (excerpts, crossfade_seconds), where excerpts is a list
                   of (start_offset, length) pairs in seconds. An empty list
                   means "fall back to plain looping" (or, for a live
                   stream, to playing the source as it arrives).
        """
        # Live streams aren't seekable and unmeasured files can't be planned.
        if xroll_is_stream or not broll_duration or not xroll_duration:
            return [], 0.0

        # Audio covers the clip on its own — one excerpt, random position.
        if xroll_duration >= broll_duration:
            offset = random.uniform(0.0, xroll_duration - broll_duration)
            return [(offset, broll_duration)], 0.0

        # Audio is shorter than the clip: chain random excerpts.
        excerpt_len = xroll_duration * self.EXCERPT_COVERAGE
        crossfade = min(self.MAX_EXCERPT_CROSSFADE_SECONDS, excerpt_len / 4)

        # n excerpts joined by n-1 crossfades run for
        # n*excerpt_len - (n-1)*crossfade, which must cover the clip.
        span = excerpt_len - crossfade
        if span <= 0:
            return [], 0.0
        needed = broll_duration + self.EXCERPT_SURPLUS_SECONDS
        count = math.ceil((needed - crossfade) / span)

        # Far too many excerpts to chain — a very short sound under a very
        # long clip. Fall back to plain looping, which is repetitive but at
        # least covers the whole clip; truncating the chain here would leave
        # the rest of the clip silent, and B-roll is never silent.
        if count > self.MAX_EXCERPTS:
            return [], 0.0
        count = max(2, count)

        max_offset = xroll_duration - excerpt_len
        excerpts = [
            (random.uniform(0.0, max_offset), excerpt_len)
            for _ in range(count)
        ]
        return excerpts, crossfade

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
        has_audio: bool = True,
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

        # Silent bed for a clip that carries no audio of its own, so the
        # segment still has an audio stream to concat against.
        if not has_audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]

        # For local files, -t after -i trims the clip to the specified duration
        if duration and not is_stream:
            cmd += ["-t", str(duration)]

        cmd += [
            "-map", "0:v:0",
            "-map", ("0:a:0" if has_audio else "1:a:0"),
            "-vf", self._build_normalize_video_filter(),
            "-r", str(self.output_fps),
        ]

        # anullsrc never ends on its own — stop with the video.
        if not has_audio:
            cmd += ["-shortest"]

        cmd += [
            "-vcodec", self.video_codec,
            "-preset", self.video_preset,
            "-acodec", self.audio_codec,
            "-ar", "48000",
            "-ac", "2",
            "-pix_fmt", self.pix_fmt,
            "-movflags", "+faststart",
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
        excerpts: Optional[list] = None,
        crossfade: float = 0.0,
    ) -> list:
        """
        Builds the FFmpeg command to layer X-roll audio over B-roll video.

        B-roll is video-only (no audio track). X-roll is audio-only. Video
        comes from input 0, audio from input 1.

        The audio bed is assembled from the excerpt plan (see
        _plan_xroll_excerpts) rather than by looping the file:

            - One excerpt — the audio covers the clip on its own, played
              from a random offset. atrim selects it.
            - Several excerpts — the audio is shorter than the clip, so
              each excerpt is taken from its own random offset and handed to
              the next with an acrossfade. This replaces `-stream_loop -1`,
              whose restart was audible as the sound changing with no cut on
              screen.
            - No excerpts — a live stream or an unmeasured file; the source
              plays from the top and is bounded by duration.

        -shortest stops encoding at whichever input ends first, which is
        always the B-roll video, so the segment matches the clip length.

        Args:
            video_source:    FFmpeg input string for the B-roll video.
            audio_source:    FFmpeg input string for the X-roll audio.
            output_path:     Path for the rendered output segment file.
            duration:        Duration in seconds (applied to B-roll length).
            video_is_stream: True if video source is a live stream.
            audio_is_stream: True if audio source is a live stream.
            excerpts:        List of (start_offset, length) pairs to play in
                             order; empty/None to play the source as-is.
            crossfade:       Seconds of overlap between consecutive excerpts.

        Returns:
            list: FFmpeg command as a list of argument strings.
        """
        cmd = ["ffmpeg", "-y"]

        # B-roll video input
        if video_is_stream:
            capture = duration if duration else self.DEFAULT_STREAM_CAPTURE_SECONDS
            cmd += ["-t", str(capture)]
        cmd += ["-i", video_source]

        # X-roll audio input
        if audio_is_stream:
            cmd += ["-t", str(duration if duration else self.DEFAULT_STREAM_CAPTURE_SECONDS)]
        elif not excerpts:
            # No excerpt plan for a local file — loop it so the clip is
            # covered. Repetitive, but B-roll is never left silent.
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", audio_source]

        # Trim to B-roll duration for local video (stream already limited above)
        if duration and not video_is_stream:
            cmd += ["-t", str(duration)]

        audio_filter = self._build_excerpt_filter(excerpts, crossfade)

        cmd += ["-map", "0:v"]              # Video from input 0 (B-roll)
        if audio_filter:
            cmd += ["-filter_complex", audio_filter, "-map", "[aout]"]
        else:
            cmd += ["-map", "1:a"]          # Audio from input 1 (X-roll)

        cmd += [
            "-vf", self._build_normalize_video_filter(),
            "-r", str(self.output_fps),
            "-shortest",         # Stop at end of B-roll video
            "-vcodec", self.video_codec,
            "-preset", self.video_preset,
            "-acodec", self.audio_codec,
            "-ar", "48000",
            "-ac", "2",
            "-pix_fmt", self.pix_fmt,
            "-movflags", "+faststart",
            output_path,
        ]

        return cmd

    def _build_excerpt_filter(
        self, excerpts: Optional[list], crossfade: float
    ) -> str:
        """
        Builds the filter graph that assembles the X-roll excerpts into one
        continuous audio bed labelled [aout].

        Each excerpt is cut from the same input with atrim, reset to zero
        with asetpts, and joined to the previous one with acrossfade. The
        input is asplit into one branch per excerpt so the file is only
        opened once.

        Args:
            excerpts:  List of (start_offset, length) pairs, or empty/None.
            crossfade: Seconds of overlap between consecutive excerpts.

        Returns:
            str: The filter_complex graph, or "" to map the source directly.
        """
        if not excerpts:
            return ""

        parts = []
        if len(excerpts) == 1:
            parts.append("[1:a]asplit=1[s0]")
        else:
            labels = "".join(f"[s{i}]" for i in range(len(excerpts)))
            parts.append(f"[1:a]asplit={len(excerpts)}{labels}")

        for i, (offset, length) in enumerate(excerpts):
            parts.append(
                f"[s{i}]atrim=start={offset:.4f}:duration={length:.4f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )

        if len(excerpts) == 1:
            parts.append("[a0]anull[aout]")
        else:
            current = "a0"
            for i in range(1, len(excerpts)):
                out = "aout" if i == len(excerpts) - 1 else f"x{i}"
                parts.append(
                    f"[{current}][a{i}]acrossfade=d={crossfade:.4f}[{out}]"
                )
                current = out

        return ";".join(parts)

    def _build_concat_command(self, segment_paths: list, output_path: str) -> list:
        """
        Builds the FFmpeg command that joins the rendered segments into the
        final film, using the concat *filter*.

        Not the concat demuxer with -c copy, which is what this used to do.
        Stream-copying AAC segments splices them at the container level, and
        because an AAC frame is 1024 samples the encoder pads each segment's
        final frame and carries its own priming samples. Copying leaves that
        padding in place at every join, so roughly the last 50ms of each
        clip's audio keeps playing at full volume over the start of the next
        clip — audible as sound bleeding across a cut. Measured at -24 dBFS
        of carry-over with the demuxer versus -71 dBFS (inaudible) here.

        The filter graph decodes every segment and re-encodes one continuous
        stream instead, so timestamps stay monotonic across each join and
        nothing survives past its own clip. This is the same approach
        _wrap_with_title_cards already uses for exactly this reason.

        The cost is re-encoding the assembled film rather than copying it.
        Every segment must carry both a video and an audio stream for the
        graph to be valid, which _render_aroll_slot guarantees.

        Args:
            segment_paths: Ordered list of paths to the rendered segments.
            output_path:   Path for the final film output file.

        Returns:
            list: FFmpeg command as a list of argument strings.
        """
        cmd = ["ffmpeg", "-y"]
        for path in segment_paths:
            cmd += ["-i", os.path.abspath(path)]

        # [0:v][0:a][1:v][1:a]...concat=n=<count>:v=1:a=1[outv][outa]
        streams = "".join(f"[{i}:v][{i}:a]" for i in range(len(segment_paths)))
        cmd += [
            "-filter_complex",
            f"{streams}concat=n={len(segment_paths)}:v=1:a=1[outv][outa]",
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", self.video_codec,
            "-preset", self.video_preset,
            "-c:a", self.audio_codec,
            "-ar", "48000",
            "-ac", "2",
            "-pix_fmt", self.pix_fmt,
            "-r", str(self.output_fps),
            "-movflags", "+faststart",
            output_path,
        ]
        return cmd

    def _build_normalize_video_filter(self) -> str:
        """
        Returns a video filter that gives every segment identical geometry.

        Local validation media can mix portrait, landscape, 4K, 1080p, and
        older low-resolution clips. Normalizing each segment before concat
        keeps the final assembly predictable and fast.

        Returns:
            str: FFmpeg filter graph for scale, pad, sample aspect, and pixel format.
        """
        return (
            f"scale={self.output_width}:{self.output_height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={self.output_width}:{self.output_height}:"
            "(ow-iw)/2:(oh-ih)/2,"
            "setsar=1,"
            f"format={self.pix_fmt}"
        )

    # ------------------------------------------------------------------
    # Concat List Writer
    # ------------------------------------------------------------------

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

        result = run_subprocess(
            cmd, self.cancel_token, capture_output=True, text=True
        )

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

        Format: film_test_<N>.<format>
        Example: film_test_1.mp4, film_test_2.mp4, etc.

        Filenames are simple and sequential for easy reference in an exhibit.
        The counter finds the highest existing number and increments it.

        Args:
            collection_id (str): The collection identifier (unused in new format).

        Returns:
            str: A unique filename string like film_test_42.mp4
        """
        if not os.path.isdir(self.films_path):
            return f"film_test_1.{self.output_format}"

        # Find highest existing number
        existing = [f for f in os.listdir(self.films_path) if f.startswith("film_test_")]
        if not existing:
            return f"film_test_1.{self.output_format}"

        numbers = []
        for fname in existing:
            try:
                num_str = fname.replace("film_test_", "").replace(f".{self.output_format}", "")
                numbers.append(int(num_str))
            except (ValueError, AttributeError):
                pass

        next_num = max(numbers) + 1 if numbers else 1
        return f"film_test_{next_num}.{self.output_format}"

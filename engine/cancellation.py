"""
cancellation.py
---------------
Dynamic Documentary Engine — Cooperative Cancellation

Lets an in-progress film generation be stopped partway through, so the web
UI can offer a working "Cancel" button instead of leaving the user to wait
out a render they no longer want.

Rendering a film is dominated by FFmpeg subprocess time, not Python time,
so a flag that is only checked between steps would leave a cancelled job
running for however long the current FFmpeg call takes. A CancellationToken
therefore does two things:

    1. Carries a thread-safe "cancelled" flag that long-running loops check
       between steps (see raise_if_cancelled).
    2. Tracks the FFmpeg subprocesses currently running under it, so
       cancel() can terminate them immediately rather than waiting for the
       current one to finish on its own.

Every FFmpeg invocation in the pipeline goes through token.run() instead of
subprocess.run(). A token of None means "not cancellable" and behaves
exactly like a plain subprocess.run(), so the CLI path and any caller that
doesn't care about cancellation is unaffected.

Usage:
    token = CancellationToken()
    # ... on another thread ...
    token.cancel()

    # in the pipeline
    token.raise_if_cancelled()
    result = run_subprocess(cmd, token, capture_output=True, text=True)

Author: Oluwafemisola David Ademoye
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import subprocess
import threading


class GenerationCancelled(Exception):
    """Raised when a film generation is stopped by an explicit cancel.

    Distinct from a render failure — callers catch this separately so a
    deliberate cancel is never reported to the user as an error.
    """


class CancellationToken:
    """A thread-safe cancel signal plus a registry of the subprocesses
    running under it.

    Safe to share across threads: the web request that starts a render and
    the later request that cancels it run on different Flask threads.
    """

    def __init__(self):
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._processes = set()

    @property
    def cancelled(self) -> bool:
        """True once cancel() has been called."""
        return self._cancelled.is_set()

    def cancel(self) -> None:
        """Signals cancellation and terminates any FFmpeg process currently
        running under this token.

        Killing the live subprocess is what makes cancellation feel
        immediate — without it, the job would keep going until the current
        FFmpeg call returned on its own.
        """
        self._cancelled.set()
        with self._lock:
            processes = list(self._processes)
        for proc in processes:
            try:
                proc.terminate()
            except OSError:
                # Already exited between the snapshot above and here.
                pass

    def raise_if_cancelled(self) -> None:
        """Raises GenerationCancelled if this token has been cancelled.

        Call between pipeline steps so a cancelled job stops promptly
        instead of running to completion and discarding the result.
        """
        if self.cancelled:
            raise GenerationCancelled("Film generation was cancelled.")

    def run(self, cmd, **kwargs):
        """subprocess.run() equivalent whose child process can be killed by
        cancel() while it is still running.

        Args:
            cmd:      Command as a list of argument strings.
            **kwargs: Passed through to subprocess.Popen (capture_output,
                      text and timeout are translated as needed).

        Returns:
            subprocess.CompletedProcess: Same shape subprocess.run() returns.

        Raises:
            GenerationCancelled: If the token was cancelled before the
                process started, or while it was running.
        """
        self.raise_if_cancelled()

        # Translate subprocess.run()-style kwargs into Popen-style ones.
        timeout = kwargs.pop("timeout", None)
        if kwargs.pop("capture_output", False):
            kwargs.setdefault("stdout", subprocess.PIPE)
            kwargs.setdefault("stderr", subprocess.PIPE)

        proc = subprocess.Popen(cmd, **kwargs)
        with self._lock:
            self._processes.add(proc)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        finally:
            with self._lock:
                self._processes.discard(proc)

        # A terminate() from cancel() shows up here as a non-zero exit. It
        # must be reported as a cancellation, not as an FFmpeg failure.
        self.raise_if_cancelled()

        return subprocess.CompletedProcess(
            proc.args, proc.returncode, stdout, stderr
        )


def run_subprocess(cmd, token=None, **kwargs):
    """Runs a subprocess under an optional CancellationToken.

    With a token, the child is killable mid-run. Without one (token=None),
    this is a plain subprocess.run() — which is what the CLI path and any
    non-cancellable caller gets.

    Args:
        cmd:      Command as a list of argument strings.
        token:    A CancellationToken, or None for a normal blocking run.
        **kwargs: Passed through to subprocess.run / Popen.

    Returns:
        subprocess.CompletedProcess
    """
    if token is None:
        return subprocess.run(cmd, **kwargs)
    return token.run(cmd, **kwargs)

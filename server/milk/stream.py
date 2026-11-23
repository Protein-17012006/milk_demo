"""Background reader that always holds the newest decoded frame of a live stream.

It runs the system `ffmpeg`, which handles RTSP, RTSPS and SRT alike, and reads raw BGR
frames from its stdout. Counting is slower than the camera's frame rate, so old frames are
dropped instead of queued: the counter always works on the newest picture. By default only
key frames are decoded, which saves most of the CPU spent on 4K video; with the camera's
I-frame interval set to one second this still gives one new picture per second.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Frame:
    image: np.ndarray  # BGR, full camera resolution
    received_at: float  # time.time() when the frame finished decoding
    seq: int


_USERINFO = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.IGNORECASE)
_SRT_LOGIN = re.compile(r"(streamid=[^:&\s]+:[^:&\s]+):[^&\s]*")
_PASSPHRASE = re.compile(r"(passphrase=)[^&\s:]*")


def redact(text: str) -> str:
    """Text with the logins and passphrases of stream URLs hidden. ffmpeg repeats the whole input URL in its
    errors, and those go to the journal and to the hub (found in the worker journal on 2026-11-22)."""
    text = _USERINFO.sub(r"\1***@", text)
    text = _SRT_LOGIN.sub(r"\1:***", text)
    return _PASSPHRASE.sub(r"\1***", text)


def _input_options(url: str, ca_file: str | None = None, tls_name: str | None = None) -> list[str]:
    """Options placed before the input URL. For RTSPS with `ca_file`, ffmpeg trusts only that certificate: the
    hub's is self-signed, and ffmpeg 9 on Windows refuses it otherwise. `tls_name` is the name in the certificate
    (milk-demo-ingest), needed because the URL holds the hub's IP address."""
    if not url.startswith(("rtsp://", "rtsps://")):
        return []
    options = ["-rtsp_transport", "tcp", "-timeout", "10000000"]  # socket timeout, microseconds
    if ca_file and url.startswith("rtsps://"):
        options += ["-tls_verify", "1", "-ca_file", ca_file]
        if tls_name:
            options += ["-verifyhost", tls_name]
    return options


def _read_exact(stream, size: int) -> bytearray | None:
    buffer = bytearray(size)
    view = memoryview(buffer)
    got = 0
    while got < size:
        n = stream.readinto(view[got:])
        if not n:
            return None
        got += n
    return buffer


class LatestFrameReader(threading.Thread):
    def __init__(
        self,
        url: str,
        keyframes_only: bool = True,
        reconnect_s: float = 2.0,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        ca_file: str | None = None,
        tls_name: str | None = None,
    ) -> None:
        super().__init__(daemon=True, name="stream-reader")
        self.url = url
        self.keyframes_only = keyframes_only
        self.reconnect_s = reconnect_s
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        self._options = _input_options(url, ca_file, tls_name)
        self.connected = False
        self.last_error: str | None = None
        self.stream_info: dict = {}
        self._cond = threading.Condition()
        self._latest: Frame | None = None
        self._seq = 0
        self._stop = threading.Event()
        self._stderr: deque[str] = deque(maxlen=20)
        self._proc: subprocess.Popen | None = None

    def stop(self) -> None:
        """Stops reading now. It also kills the running ffmpeg, so a sampling window closes at once instead of
        after the socket timeout."""
        self._stop.set()
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass  # it had already exited

    def _probe(self) -> tuple[int, int, str]:
        cmd = [
            self.ffprobe,
            "-v",
            "error",
            *self._options,
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "json",
            self.url,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError((result.stderr.decode(errors="replace").strip().splitlines() or ["ffprobe failed"])[-1])
        streams = json.loads(result.stdout).get("streams") or []
        if not streams:
            raise RuntimeError("no video track in the stream")
        s = streams[0]
        return int(s["width"]), int(s["height"]), str(s.get("codec_name", "?"))

    def _drain(self, pipe) -> None:
        for line in iter(pipe.readline, b""):
            self._stderr.append(line.decode(errors="replace").strip())

    def run(self) -> None:
        while not self._stop.is_set():
            proc = None
            try:
                width, height, codec = self._probe()
                if self._stop.is_set():
                    break  # stopped while ffprobe was running
                cmd = [self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", *self._options]
                if self.keyframes_only:
                    cmd += ["-skip_frame", "nokey"]
                cmd += [
                    "-i",
                    self.url,
                    "-map",
                    "0:v:0",
                    "-an",
                    "-sn",
                    "-fps_mode",
                    "passthrough",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "bgr24",
                    "pipe:1",
                ]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                self._proc = proc
                threading.Thread(target=self._drain, args=(proc.stderr,), daemon=True).start()
                self.stream_info = {
                    "codec": codec,
                    "width": width,
                    "height": height,
                    "keyframes_only": self.keyframes_only,
                }
                if self.last_error:
                    log.info("stream connected again: %s", self.stream_info)
                self.connected, self.last_error = True, None
                size = width * height * 3
                while not self._stop.is_set():
                    raw = _read_exact(proc.stdout, size)
                    if raw is None:
                        raise RuntimeError(self._stderr[-1] if self._stderr else "stream ended")
                    image = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
                    with self._cond:
                        self._seq += 1
                        self._latest = Frame(image, time.time(), self._seq)
                        self._cond.notify_all()
            except Exception as exc:  # noqa: BLE001 - any failure means reconnect
                if self._stop.is_set():
                    break  # the worker closed the stream itself (stop()); not an error
                message = redact(f"{type(exc).__name__}: {exc}")
                if message != self.last_error:
                    log.warning("stream unavailable: %s", message)
                self.last_error = message
            finally:
                self.connected = False
                self._proc = None
                if proc is not None:
                    proc.kill()
                    proc.wait()
            self._stop.wait(self.reconnect_s)

    def newer_than(self, seq: int, timeout: float) -> Frame | None:
        """The newest frame if it is newer than `seq`, waiting up to `timeout` seconds."""
        with self._cond:
            if self._latest is None or self._latest.seq <= seq:
                self._cond.wait(timeout)
            latest = self._latest
        return latest if latest is not None and latest.seq > seq else None

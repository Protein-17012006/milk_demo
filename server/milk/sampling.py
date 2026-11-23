"""When the worker reads the camera stream: all the time, or in short windows.

Reading the stream continuously costs AWS data transfer for every hour of video (hub -> worker) and for every
picture sent back (worker -> CloudFront -> hub), while the website needs one official count per hour. With
MILK_SAMPLE_EVERY_S = 300 and MILK_SAMPLE_FOR_S = 30 the worker opens the stream for 30 s at 12:00, 12:05, ...
and closes it in between; the hub's MediaMTX pulls the camera on demand, so it stops pulling too.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class Reader(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class Sampler:
    """Opens a reader at the start of every window and stops it at the window's end. Windows start on the
    multiples of `every_s` seconds of the clock and last `for_s` seconds; `every_s` <= 0 means one reader that
    stays open."""

    def __init__(self, every_s: float, for_s: float, open_reader: Callable[[], Reader]) -> None:
        self.every_s = float(every_s)
        self.for_s = float(for_s)
        self._open = open_reader
        self._reader: Reader | None = None
        self._window: int | None = None

    @property
    def continuous(self) -> bool:
        return self.every_s <= 0

    def in_window(self, now: float) -> bool:
        return self.continuous or now % self.every_s < self.for_s

    def next_start(self, now: float) -> float:
        return (now // self.every_s + 1) * self.every_s

    def reader_at(self, now: float) -> tuple[Reader | None, bool]:
        """The reader to use at `now` (None between windows) and whether it was opened by this call."""
        if not self.in_window(now):
            self.close()
            return None, False
        window = 0 if self.continuous else int(now // self.every_s)
        if self._reader is not None and self._window == window:
            return self._reader, False
        self.close()
        self._reader, self._window = self._open(), window
        self._reader.start()
        return self._reader, True

    def describe(self, now: float) -> dict | None:
        """For the hub's status: how often the worker reads the stream and when it opens next."""
        if self.continuous:
            return None
        return {"every_s": self.every_s, "for_s": self.for_s, "next_at": self.next_start(now)}

    def close(self) -> None:
        if self._reader is not None:
            self._reader.stop()
        self._reader, self._window = None, None

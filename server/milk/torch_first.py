"""Loads torch before any other native library on Windows.

On the Windows GPU worker (HUYHOANG, 23/11/2026) the worker died with an access violation (0xC0000005) while
lancedb imported pyarrow. The cause is the order in which DLLs take Windows thread-local storage (TLS) slots.
When torch loads, the CUDA libraries it ships (cusolver64_11.dll and the DLLs it pulls in) take a block of about
40 slots. If that block starts at slot 62 or 63, arrow.dll (pyarrow) later crashes while it sets up its own
thread-local data. Slot 63 is the last slot kept inside each thread's block, so in that layout it falls among
the block's first two. Whatever loads before torch moves the block: the worker loaded ssl (urllib.request) and
cv2 first, which put it exactly there.

Measured on HUYHOANG with torch 2.11.0+cu128 and lancedb 0.40.0:
- The crash happens exactly when the block starts at 62 or 63.
- Holding slot 63 prevents it; holding 64, 65 or 66 does not.
- With torch loaded first, the block starts near slot 50 every time and pyarrow loads normally.

After upgrading torch or pyarrow on a Windows machine, run tests/test_torch_first.py there.
"""

from __future__ import annotations


def load_torch_first(platform: str) -> bool:
    """Imports torch on Windows when it is installed; returns whether it did."""
    if platform != "win32":
        return False
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True

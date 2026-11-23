"""Milk shelf counter: live stock counting from a store CCTV stream."""

import sys

from .torch_first import load_torch_first

load_torch_first(sys.platform)  # before any milk module loads another native library: see torch_first.py

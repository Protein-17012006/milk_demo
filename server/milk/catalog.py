"""The product name the worker writes for each model label, from skus.json (the backend's alias table maps the same
labels to the official product names; tests/test_long_adapter.py keeps the two in step)."""

from __future__ import annotations

import json
from pathlib import Path

SKUS = Path(__file__).with_name("skus.json")


def product_names() -> dict[str, str]:
    return {s["id"]: s["name"] for s in json.loads(SKUS.read_text("utf-8"))}

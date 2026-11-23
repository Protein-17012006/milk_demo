"""On Windows the milk package loads torch before any other native library (see milk/torch_first.py)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from milk.torch_first import load_torch_first

SERVER = Path(__file__).resolve().parents[1] / "server"


@pytest.fixture
def fake_torch(tmp_path, monkeypatch):
    """A stand-in torch package, so the tests do not need the real one."""
    (tmp_path / "torch").mkdir()
    (tmp_path / "torch" / "__init__.py").write_text("LOADED = True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    real = sys.modules.pop("torch", None)
    yield
    sys.modules.pop("torch", None)
    if real is not None:
        sys.modules["torch"] = real


def test_loads_torch_on_windows(fake_torch):
    assert load_torch_first("win32") is True
    assert sys.modules["torch"].LOADED


def test_leaves_other_platforms_alone(fake_torch):
    assert load_torch_first("linux") is False
    assert "torch" not in sys.modules


def test_machines_without_torch_carry_on(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)  # makes "import torch" raise ImportError
    assert load_torch_first("win32") is False


@pytest.mark.skipif(
    sys.platform != "win32" or not all(importlib.util.find_spec(m) for m in ("torch", "cv2", "pyarrow")),
    reason="needs the Windows GPU worker's libraries (torch, cv2, pyarrow)",
)
def test_worker_import_order_leaves_pyarrow_working():
    # milk.counter loads ssl (urllib.request); the long pipeline then loads cv2, torch and lancedb's pyarrow.
    # In that order pyarrow crashed the process on HUYHOANG (0xC0000005) until milk loaded torch first.
    code = "import milk.counter, cv2, torch, pyarrow.dataset"
    result = subprocess.run([sys.executable, "-c", code], cwd=SERVER, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[-2000:]}"

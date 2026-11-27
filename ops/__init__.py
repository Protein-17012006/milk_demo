"""Tools that run on the counting machine beside the worker (operations-loop design 5.2): the job runner that
carries out what the Model page asks, and the tool that makes a release folder.

They read releases with the worker's own code (server/milk/release.py) and share names with the backend
(backend/model_versions.py), so both folders are put on the import path here.
"""

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for _folder in ("server", "backend"):
    _path = str(_REPO / _folder)
    if _path not in sys.path:
        sys.path.insert(0, _path)

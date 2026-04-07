from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
for _p in (_SRC.resolve(), Path(__file__).resolve().parent):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

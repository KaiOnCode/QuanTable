from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    # `uv run pytest` does not install the repo as a package, so tests add the
    # repo root explicitly to import the local `broker` package.
    sys.path.insert(0, str(ROOT))

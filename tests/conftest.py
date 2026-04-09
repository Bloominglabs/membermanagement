from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
for candidate in (ROOT_DIR / ".pkg", ROOT_DIR / "backend", ROOT_DIR):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


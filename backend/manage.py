#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def bootstrap_pythonpath() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    vendor_dir = root_dir / ".pkg"
    for path in (root_dir, vendor_dir):
        path_str = str(path)
        if path.exists() and path_str not in sys.path:
            sys.path.insert(0, path_str)


def main() -> None:
    bootstrap_pythonpath()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Install the dependencies from requirements.txt "
            "or vendor them into .pkg."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

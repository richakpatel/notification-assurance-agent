"""
Zero-install entry point for the Customer Notification Assurance Agent demo.

This is a thin wrapper so the demo runs straight from a clone with no
`pip install` step. It just puts `src/` on the path and calls the package's
console demo (`notification_agent.__main__:main`), which does all the work.

Run it from the repo root:
    python3 scripts/run_demo.py

Equivalent, after `pip install -e .`:
    python3 -m notification_agent      (or the `notification-agent-demo` command)

ALL DATA IS SYNTHETIC / QA ONLY.
"""

from __future__ import annotations

import pathlib
import sys

# Make the src/ package importable without installing.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from notification_agent.__main__ import main

if __name__ == "__main__":
    main()

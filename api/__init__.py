"""
HTTP API layer for the Customer Notification Assurance Agent.

Exposes the agent as a small JSON service using ONLY the Python standard
library (`http.server`) — no FastAPI, Flask, or other third-party web
framework — so the whole project stays dependency-free and runs anywhere.

Run it with:
    python3 api/server.py            # serves on http://127.0.0.1:8000
"""

from __future__ import annotations

from .server import build_app, run  # noqa: F401

__all__ = ["build_app", "run"]

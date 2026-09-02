"""
Zero-dependency JSON API for the Customer Notification Assurance Agent.

Uses only the Python standard library (`http.server`), so it runs with no
`pip install` step and keeps the project dependency-free.

Endpoints
---------
GET  /health
    Liveness probe. -> {"status": "ok", "version": "..."}

GET  /demo
    Runs all three processes (MAS, MCN, THRESHOLD) over the built-in synthetic
    sample records and returns every cycle report as JSON. This is the same data
    the CLI demo (`scripts/run_demo.py`) prints.

POST /reconcile
    Run a single cycle over caller-supplied synthetic records.
    Body: {
        "notification_type": "MAS" | "MCN" | "THRESHOLD",
        "period": "2026-10",
        "cycle_start": "2026-10-01",
        "records": [ { ...Record fields... }, ... ]
    }
    -> a single cycle report as JSON.

ALL DATA IS SYNTHETIC / QA ONLY. The agent is read-only: it never sends or
mutates a notification.

Usage:
    python3 api/server.py                 # http://127.0.0.1:8000
    python3 api/server.py --port 9000
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Zero-install convenience: make the src/ package importable from a clone.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from notification_agent import (  # noqa: E402
    MAS,
    MCN,
    THRESHOLD,
    NotificationAssuranceAgent,
    Record,
    __version__,
    build_records,
)

_VALID_TYPES = {MAS, MCN, THRESHOLD}


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #
def _finding_to_dict(f) -> dict:
    return dataclasses.asdict(f)


def _report_to_dict(report) -> dict:
    """Flatten a CycleReport into a JSON-serializable dict."""
    r = report.result
    return {
        "notification_type": r.notification_type,
        "period": r.period,
        "counts": {
            "eligible": r.eligible_count,
            "delivered": r.delivered_count,
            "missed": report.missed_count,
            "escalations": len(report.escalations),
        },
        "eligible_ids": list(r.eligible_ids),
        "stamped_ids": list(r.stamped_ids),
        "missed_ids": list(r.missed_ids),
        "findings": [_finding_to_dict(f) for f in report.findings],
        "escalations": [_finding_to_dict(f) for f in report.escalations],
        "trace": list(report.trace),
    }


def _record_from_dict(d: dict) -> Record:
    """Build a synthetic Record from a JSON object, ignoring unknown keys."""
    field_names = {fld.name for fld in dataclasses.fields(Record)}
    kwargs = {k: v for k, v in d.items() if k in field_names}
    if "record_id" not in kwargs:
        raise ValueError("each record needs a 'record_id'")
    return Record(**kwargs)


# --------------------------------------------------------------------------- #
# Request handler
# --------------------------------------------------------------------------- #
def build_app(agent: NotificationAssuranceAgent | None = None):
    """Return a BaseHTTPRequestHandler subclass bound to one agent instance."""
    the_agent = agent or NotificationAssuranceAgent()

    class Handler(BaseHTTPRequestHandler):
        server_version = "NotificationAssuranceAgent/" + __version__

        # -- helpers --------------------------------------------------------
        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        # keep the console quiet-ish; still show method + path
        def log_message(self, fmt, *args):  # noqa: A003
            sys.stderr.write("  api  " + (fmt % args) + "\n")

        # -- routes ---------------------------------------------------------
        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send_json({"status": "ok", "version": __version__})
                return

            if self.path == "/demo":
                records = build_records()
                reports = {
                    "MAS": the_agent.run_cycle(MAS, "2026-10", "2026-10-01", records),
                    "MCN": the_agent.run_cycle(MCN, "2026-10", "2026-10-01", records),
                    "THRESHOLD": the_agent.run_cycle(THRESHOLD, "2026-10-05", "2026-10-05", records),
                }
                self._send_json(
                    {"note": "synthetic sample data", "cycles":
                        {k: _report_to_dict(v) for k, v in reports.items()}}
                )
                return

            self._send_json({"error": "not found", "path": self.path}, status=404)

        def do_POST(self):  # noqa: N802
            if self.path != "/reconcile":
                self._send_json({"error": "not found", "path": self.path}, status=404)
                return
            try:
                body = self._read_body()
                nt = body.get("notification_type")
                if nt not in _VALID_TYPES:
                    raise ValueError(f"notification_type must be one of {sorted(_VALID_TYPES)}")
                period = body.get("period")
                cycle_start = body.get("cycle_start")
                if not period or not cycle_start:
                    raise ValueError("'period' and 'cycle_start' are required")
                records = [_record_from_dict(d) for d in body.get("records", [])]
                report = the_agent.run_cycle(nt, period, cycle_start, records)
                self._send_json(_report_to_dict(report))
            except (ValueError, json.JSONDecodeError, TypeError) as exc:
                self._send_json({"error": str(exc)}, status=400)

    return Handler


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    handler = build_app()
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"Notification Assurance Agent API  (v{__version__})")
    print(f"  serving on http://{host}:{port}   (Ctrl-C to stop)")
    print("  GET  /health     GET  /demo     POST /reconcile")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  shutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Notification Assurance Agent JSON API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run(args.host, args.port)

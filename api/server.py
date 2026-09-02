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


def _esc(text) -> str:
    """Minimal HTML escaping for the dashboard."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _render_index_html(cycles: dict) -> str:
    """Render the live demo results as a self-contained browser dashboard."""
    sev_color = {"high": "#D94A4A", "medium": "#E0A800", "low": "#0E9F8E"}

    sections = []
    for name, report in cycles.items():
        c = report["counts"]
        rows = []
        for f in report["findings"]:
            color = sev_color.get(f["severity"], "#666")
            missed = "yes" if f["counts_as_missed"] else "no"
            esc = "yes" if f["escalate"] else "no"
            rows.append(
                f"<tr>"
                f"<td class='mono'>{_esc(f['record_id'])}</td>"
                f"<td class='mono'>{_esc(f['observed'])}</td>"
                f"<td class='mono'>{_esc(f['reason_code'])}</td>"
                f"<td>{_esc(f['category'])}</td>"
                f"<td style='text-align:center'>{missed}</td>"
                f"<td style='text-align:center'>{esc}</td>"
                f"<td style='text-align:center'><span class='pill' style='background:{color}'>{_esc(f['severity'])}</span></td>"
                f"<td style='text-align:right'>{f['confidence']:.3f}</td>"
                f"</tr>"
            )
        sections.append(f"""
      <section class="cycle">
        <h2>{_esc(name)} <span class="period">period {_esc(report['period'])}</span></h2>
        <div class="counts">
          <span class="stat"><b>{c['eligible']}</b> eligible</span>
          <span class="stat"><b>{c['delivered']}</b> delivered</span>
          <span class="stat missed"><b>{c['missed']}</b> missed</span>
          <span class="stat esc"><b>{c['escalations']}</b> escalations</span>
        </div>
        <table>
          <thead><tr>
            <th>record</th><th>observed</th><th>reason code</th><th>category</th>
            <th>missed</th><th>escalate</th><th>severity</th><th>conf.</th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </section>""")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notification Assurance Agent</title>
<style>
  :root {{ --band:#1F2A4C; --accent:#2B59C3; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
          color:#1a1a2e; background:#f4f6fb; }}
  header {{ background:var(--band); color:#fff; padding:28px 32px; }}
  header h1 {{ margin:0 0 6px; font-size:22px; }}
  header p {{ margin:0; opacity:.85; font-size:14px; }}
  .synthetic {{ display:inline-block; margin-top:10px; padding:3px 10px; border-radius:12px;
                background:#0E9F8E; color:#fff; font-size:12px; font-weight:600; }}
  main {{ max-width:1040px; margin:0 auto; padding:24px 32px 48px; }}
  .cycle {{ background:#fff; border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,.08);
            padding:18px 20px; margin:18px 0; }}
  .cycle h2 {{ margin:0 0 12px; font-size:18px; color:var(--band); }}
  .period {{ font-size:13px; font-weight:400; color:#888; }}
  .counts {{ margin-bottom:12px; }}
  .stat {{ display:inline-block; margin-right:16px; font-size:13px; color:#555; }}
  .stat b {{ font-size:17px; color:var(--band); }}
  .stat.missed b {{ color:#D94A4A; }} .stat.esc b {{ color:#E0A800; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ padding:7px 9px; border-bottom:1px solid #eee; text-align:left; }}
  th {{ background:#f0f2f8; color:var(--band); font-weight:600; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
  .pill {{ color:#fff; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:600; }}
  .endpoints {{ font-size:13px; color:#555; }}
  .endpoints code {{ background:#eef; padding:2px 6px; border-radius:4px; }}
  footer {{ text-align:center; color:#999; font-size:12px; padding:20px; }}
</style></head>
<body>
  <header>
    <h1>Customer Notification Assurance Agent</h1>
    <p>Live reconciliation-and-diagnosis pass across all three processes.</p>
    <span class="synthetic">ALL DATA SYNTHETIC / ANONYMIZED</span>
  </header>
  <main>
    <p class="endpoints">API endpoints:
      <code>GET /health</code> &nbsp; <code>GET /demo</code> (raw JSON) &nbsp;
      <code>POST /reconcile</code> &nbsp; | &nbsp; this page = <code>GET /</code></p>
    {''.join(sections)}
  </main>
  <footer>Notification Assurance Agent v{__version__} &middot; zero-dependency stdlib server</footer>
</body></html>"""


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

        def _send_html(self, html: str, status: int = 200) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
        def _run_demo_cycles(self) -> dict:
            records = build_records()
            reports = {
                "MAS": the_agent.run_cycle(MAS, "2026-10", "2026-10-01", records),
                "MCN": the_agent.run_cycle(MCN, "2026-10", "2026-10-01", records),
                "THRESHOLD": the_agent.run_cycle(THRESHOLD, "2026-10-05", "2026-10-05", records),
            }
            return {k: _report_to_dict(v) for k, v in reports.items()}

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                html = _render_index_html(self._run_demo_cycles())
                self._send_html(html)
                return

            if self.path == "/health":
                self._send_json({"status": "ok", "version": __version__})
                return

            if self.path == "/demo":
                self._send_json({"note": "synthetic sample data",
                                 "cycles": self._run_demo_cycles()})
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
    print(f"  open http://{host}:{port}/  in a browser for the live dashboard")
    print("  GET  /           GET  /health     GET  /demo     POST /reconcile")
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

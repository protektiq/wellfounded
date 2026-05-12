"""Side-by-side HTML viewer for two ``RunManifest`` result files.

``python -m evals.view <result_a.json> <result_b.json> [--port 8765]``

Boots a single-page ``http.server`` HTTPServer bound to ``127.0.0.1`` only so the
results never leak onto the network. Both manifests are validated against the
``RunManifest`` schema at startup; any mismatch fails fast.

Stays stdlib-only (no Flask/Starlette/Jinja) to keep the dependency surface
small per ``.cursorrules``: this is review tooling, not production code.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from evals.fixtures import FixtureRun, RunManifest

_HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Wellfounded eval diff</title>
<style>
  :root {
    --bg: #fafaf7;
    --fg: #1a1a1a;
    --muted: #777;
    --border: #ddd;
    --improve: #2a7a2a;
    --regress: #b22222;
    --neutral: #555;
    --row-alt: #f3f3ed;
  }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: var(--bg); color: var(--fg); margin: 0; padding: 24px; }
  h1 { font-size: 1.25rem; margin: 0 0 4px; }
  .meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 16px; }
  .meta code { background: #eee; padding: 1px 4px; border-radius: 3px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td {
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
  }
  th { background: #efeee9; font-weight: 600; }
  tr:nth-child(even) td { background: var(--row-alt); }
  td.num { font-variant-numeric: tabular-nums; text-align: right; }
  .delta-up { color: var(--improve); font-weight: 600; }
  .delta-down { color: var(--regress); font-weight: 600; }
  .delta-zero { color: var(--neutral); }
  .err { color: var(--regress); font-style: italic; }
  .footer { color: var(--muted); font-size: 0.8rem; margin-top: 24px; }
</style>
</head>
<body>
"""

_HTML_FOOT = "</body></html>\n"


def _load_manifest(path: Path) -> RunManifest:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return RunManifest.model_validate(data)


def _format_score(value: float | None) -> str:
    if value is None:
        return "&mdash;"
    return f"{value:.3f}"


def _format_delta(left: float | None, right: float | None) -> str:
    if left is None or right is None:
        return "<span class='delta-zero'>n/a</span>"
    diff = right - left
    if abs(diff) < 1e-9:
        return "<span class='delta-zero'>0.000</span>"
    if diff > 0:
        return f"<span class='delta-up'>+{diff:.3f}</span>"
    return f"<span class='delta-down'>{diff:.3f}</span>"


def _format_passed(value: bool | None) -> str:
    if value is None:
        return "&mdash;"
    return "pass" if value else "fail"


def _row_html(
    fixture_id: str,
    scorer_left: str | None,
    scorer_right: str | None,
    left: FixtureRun | None,
    right: FixtureRun | None,
) -> str:
    score_l = left.result.score if left else None
    score_r = right.result.score if right else None
    err_l = left.result.error if left else None
    err_r = right.result.error if right else None
    scorer_display = scorer_right or scorer_left or "&mdash;"
    err_cell = ""
    if err_l or err_r:
        msgs: list[str] = []
        if err_l:
            msgs.append(f"A: {err_l}")
        if err_r:
            msgs.append(f"B: {err_r}")
        err_cell = f"<div class='err'>{html.escape(' | '.join(msgs))}</div>"
    return (
        "<tr>"
        f"<td>{html.escape(fixture_id)}{err_cell}</td>"
        f"<td>{html.escape(scorer_display)}</td>"
        f"<td class='num'>{_format_score(score_l)}</td>"
        f"<td class='num'>{_format_score(score_r)}</td>"
        f"<td class='num'>{_format_delta(score_l, score_r)}</td>"
        f"<td>{_format_passed(left.result.passed if left else None)}</td>"
        f"<td>{_format_passed(right.result.passed if right else None)}</td>"
        "</tr>"
    )


def render_diff(left: RunManifest, right: RunManifest) -> str:
    """Render the side-by-side HTML page for two manifests."""
    by_id_left = {fr.fixture_id: fr for fr in left.fixtures}
    by_id_right = {fr.fixture_id: fr for fr in right.fixtures}
    all_ids = sorted(set(by_id_left) | set(by_id_right))

    rows: list[str] = []
    for fid in all_ids:
        left_fr = by_id_left.get(fid)
        right_fr = by_id_right.get(fid)
        rows.append(
            _row_html(
                fid,
                left_fr.scorer if left_fr is not None else None,
                right_fr.scorer if right_fr is not None else None,
                left_fr,
                right_fr,
            ),
        )

    left_sha = html.escape(left.git_sha)
    left_ts = html.escape(left.started_at)
    right_sha = html.escape(right.git_sha)
    right_ts = html.escape(right.started_at)
    meta = (
        "<h1>Eval diff</h1>"
        "<div class='meta'>"
        f"Category: <code>{html.escape(left.category)}</code> &middot; "
        f"A: <code>{left_sha}</code> ({left_ts}) &middot; "
        f"B: <code>{right_sha}</code> ({right_ts})"
        "</div>"
    )

    if left.category != right.category:
        meta += (
            "<div class='err'>Manifests are from different categories; "
            "diff may not be meaningful.</div>"
        )

    table = (
        "<table>"
        "<thead><tr>"
        "<th>Fixture</th><th>Scorer</th><th>Score A</th><th>Score B</th>"
        "<th>Δ</th><th>Passed A</th><th>Passed B</th>"
        "</tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )

    if not rows:
        table = "<p class='meta'>No fixtures in either manifest.</p>"

    footer = (
        "<div class='footer'>Wellfounded eval harness. "
        "Read-only viewer; no data is sent to the network.</div>"
    )
    return _HTML_HEAD + meta + table + footer + _HTML_FOOT


class _DiffHandler(BaseHTTPRequestHandler):
    """One-page handler shared across requests via the server's ``html_body``."""

    server: _DiffServer

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path not in ("/", "/index.html"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        body = self.server.html_body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - http.server API
        return  # silence stdlib's default per-request stderr noise


class _DiffServer(HTTPServer):
    html_body: str = ""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evals.view",
        description="Serve a side-by-side HTML diff of two eval result manifests.",
    )
    parser.add_argument("left", type=Path, help="First (baseline) result JSON.")
    parser.add_argument("right", type=Path, help="Second (candidate) result JSON.")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Localhost port to bind (1024-65535).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not 1024 <= args.port <= 65535:
        print("error: --port must be between 1024 and 65535", file=sys.stderr)
        return 2
    left = _load_manifest(args.left)
    right = _load_manifest(args.right)
    body = render_diff(left, right)

    server = _DiffServer(("127.0.0.1", args.port), _DiffHandler)
    server.html_body = body
    print(f"Serving eval diff on http://127.0.0.1:{args.port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

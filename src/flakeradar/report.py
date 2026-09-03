"""Self-contained HTML report generation.

No CDN calls, no external JS frameworks - the report is a single file you
can commit, email, or attach to a ticket, and it will still render
correctly with no network access.
"""

from __future__ import annotations

import html
import json
import time
from pathlib import Path
from typing import List, Optional

from .clustering import cluster_failures
from .scoring import FlakinessResult
from .storage import HistoryEntry

_OUTCOME_COLOR = {
    1: "#22c55e",  # pass
    0: "#ef4444",  # fail
}


def _sparkline_svg(outcomes: List[str], width: int = 220, height: int = 28) -> str:
    binary = [1 if o == "passed" else (0 if o in ("failed", "error") else None) for o in outcomes]
    binary = [b for b in binary if b is not None]
    if not binary:
        return "<svg></svg>"
    n = len(binary)
    cell_w = max(width / max(n, 1), 3)
    total_w = round(cell_w * n, 1)
    rects = []
    for i, b in enumerate(binary):
        x = round(i * cell_w, 1)
        color = _OUTCOME_COLOR[b]
        rects.append(f'<rect x="{x}" y="0" width="{max(cell_w - 1, 1)}" height="{height}" fill="{color}" />')
    return (
        f'<svg viewBox="0 0 {total_w} {height}" width="{min(width, total_w)}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(rects)}</svg>'
    )


_CLASS_BADGE = {
    "flaky": ("#fef3c7", "#92400e", "FLAKY"),
    "broken": ("#fee2e2", "#991b1b", "BROKEN"),
    "stable": ("#dcfce7", "#166534", "STABLE"),
    "insufficient_data": ("#e5e7eb", "#374151", "LOW DATA"),
}

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>flakeradar report</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0; padding: 32px; background: #0b0f14; color: #e5e7eb;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
  .subtitle {{ color: #9ca3af; font-size: 13px; margin-bottom: 24px; }}
  .summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .summary .card {{
    background: #131a22; border: 1px solid #1f2937; border-radius: 10px;
    padding: 14px 18px; min-width: 120px;
  }}
  .summary .card .n {{ font-size: 24px; font-weight: 700; }}
  .summary .card .l {{ font-size: 12px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.04em; }}
  table {{ width: 100%; border-collapse: collapse; background: #131a22; border-radius: 10px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #1f2937; font-size: 13px; }}
  th {{ color: #9ca3af; font-weight: 600; cursor: pointer; user-select: none; }}
  th:hover {{ color: #e5e7eb; }}
  tr:hover td {{ background: #182028; }}
  .nodeid {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.03em;
  }}
  .score {{ font-variant-numeric: tabular-nums; }}
  footer {{ margin-top: 24px; color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
  <h1>flakeradar report</h1>
  <div class="subtitle">Generated {generated_at} &middot; {run_count} run(s) analyzed</div>

  <div class="summary">
    <div class="card"><div class="n">{total_tests}</div><div class="l">Tests tracked</div></div>
    <div class="card"><div class="n" style="color:#f59e0b">{flaky_count}</div><div class="l">Flaky</div></div>
    <div class="card"><div class="n" style="color:#ef4444">{broken_count}</div><div class="l">Consistently failing</div></div>
    <div class="card"><div class="n" style="color:#22c55e">{stable_count}</div><div class="l">Stable</div></div>
  </div>

  <table id="results">
    <thead>
      <tr>
        <th onclick="sortBy(0)">Test</th>
        <th onclick="sortBy(1)">Status</th>
        <th onclick="sortBy(2)">History ({window} most recent)</th>
        <th onclick="sortBy(3)">Runs</th>
        <th onclick="sortBy(4)">Fail rate</th>
        <th onclick="sortBy(5)">Score</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>

  <footer>
    flakeradar &middot; score = 0.6 &times; transition_rate + 0.4 &times; balance &middot;
    threshold for "flaky" classification: {threshold}
  </footer>

<script>
function sortBy(col) {{
  const tbody = document.querySelector('#results tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const numeric = col >= 3;
  rows.sort((a, b) => {{
    let av = a.children[col].getAttribute('data-sort') || a.children[col].innerText;
    let bv = b.children[col].getAttribute('data-sort') || b.children[col].innerText;
    if (numeric) {{ av = parseFloat(av) || 0; bv = parseFloat(bv) || 0; return bv - av; }}
    return av.localeCompare(bv);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
</script>
</body>
</html>
"""


def _row_html(nodeid: str, result: FlakinessResult, history: List[HistoryEntry], window: int) -> str:
    recent = history[-window:]
    outcomes = [h.outcome for h in recent]
    bg, fg, label = _CLASS_BADGE.get(result.classification, _CLASS_BADGE["insufficient_data"])
    return f"""      <tr>
        <td class="nodeid">{html.escape(nodeid)}</td>
        <td data-sort="{result.classification}"><span class="badge" style="background:{bg};color:{fg}">{label}</span></td>
        <td>{_sparkline_svg(outcomes)}</td>
        <td data-sort="{result.total_runs}">{result.total_runs}</td>
        <td data-sort="{result.fail_rate}">{result.fail_rate:.0%}</td>
        <td data-sort="{result.score}" class="score">{result.score:.2f}</td>
      </tr>"""


def generate_html_report(
    results: List[FlakinessResult],
    histories: dict,
    run_count: int,
    threshold: float,
    window: int = 40,
) -> str:
    ordered = sorted(results, key=lambda r: (-r.score, r.nodeid))
    rows = "\n".join(_row_html(r.nodeid, r, histories.get(r.nodeid, []), window) for r in ordered)

    flaky = sum(1 for r in results if r.classification == "flaky")
    broken = sum(1 for r in results if r.classification == "broken")
    stable = sum(1 for r in results if r.classification == "stable")

    return _TEMPLATE.format(
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        run_count=run_count,
        total_tests=len(results),
        flaky_count=flaky,
        broken_count=broken,
        stable_count=stable,
        rows=rows or "      <tr><td colspan=\"6\">No data yet - run pytest with --flakeradar first.</td></tr>",
        threshold=threshold,
        window=window,
    )


def write_report(path: Path, html_content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_content, encoding="utf-8")


def generate_json_report(results: List[FlakinessResult], run_count: int, threshold: float) -> str:
    """Machine-readable summary, for custom dashboards or other tooling."""
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_count": run_count,
        "flakiness_threshold": threshold,
        "tests": [
            {
                "nodeid": r.nodeid,
                "classification": r.classification,
                "score": r.score,
                "total_runs": r.total_runs,
                "pass_count": r.pass_count,
                "fail_count": r.fail_count,
                "other_count": r.other_count,
                "fail_rate": r.fail_rate,
                "transition_rate": r.transition_rate,
                "last_outcome": r.last_outcome,
            }
            for r in sorted(results, key=lambda r: (-r.score, r.nodeid))
        ],
    }
    return json.dumps(payload, indent=2)

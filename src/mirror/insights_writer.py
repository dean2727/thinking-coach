from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .paths import coaching_sessions_dir
from .schema import CoachingReport


def report_filename(ts: datetime | None = None, slug: str = "mirror-coach") -> str:
    ts = ts or datetime.now()
    safe_slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in slug).strip("-")
    return f"{ts.strftime('%Y-%m-%d_%H-%M-%S')}_{safe_slug}.md"


def report_to_markdown(report: CoachingReport) -> str:
    lines = [
        f"# {report.title}",
        "",
        f"Generated: {report.generated_at.isoformat()}",
        "",
        "## What improved",
        *[f"- {item}" for item in report.growth_highlights],
        "",
        "## Where reps may be missing",
        *[f"- {item}" for item in report.growth_edges],
        "",
        "## One practice for the next session",
        f"- {report.next_practice or 'No practice selected.'}",
        "",
        "## Goal check-in",
        *([f"- {item}" for item in report.goal_status] or ["- No active goals configured."]),
        "",
        "## Suggested prompt patterns",
        *[f"- {item}" for item in report.prompt_patterns],
        "",
        "## Evidence limits",
        report.evidence_limits,
        "",
    ]
    return "\n".join(lines)


def write_report(report: CoachingReport, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or coaching_sessions_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / report_filename(report.generated_at)
    path.write_text(report_to_markdown(report), encoding="utf-8")
    report.output_path = str(path)
    return path

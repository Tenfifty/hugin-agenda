"""Sync a toggled journal checkbox back to gtd.md."""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import AgendaConfig, load_config


CHECKBOX_RE = re.compile(r"^([ \t]*-\s+\[)([ xX])(\]\s+)(.*\S)\s*$")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True)
class CheckboxLine:
    checked: bool
    text: str


@dataclass(frozen=True)
class SyncResult:
    matched: int
    changed: int
    status: str


def parse_checkbox_line(line: str) -> CheckboxLine | None:
    match = CHECKBOX_RE.match(line)
    if not match:
        return None
    return CheckboxLine(checked=match.group(2).lower() == "x", text=match.group(4))


def _checkbox_text(line: str) -> str | None:
    parsed = parse_checkbox_line(line)
    return parsed.text if parsed else None


def _replace_checkbox_state(line: str, checked: bool) -> str:
    match = CHECKBOX_RE.match(line)
    if not match:
        return line
    marker = "x" if checked else " "
    return f"{match.group(1)}{marker}{match.group(3)}{match.group(4)}"


def excluded_section_headings(cfg: AgendaConfig) -> set[str]:
    additions_heading, removals_heading = cfg.resolved_overlay_headings()
    return {
        additions_heading,
        removals_heading,
        "Additions",
        "Removals",
        "Tillägg",
        "Borttagningar",
    }


def _candidate_indexes(
    lines: list[str], target_text: str, excluded_h2s: set[str]
) -> list[int]:
    indexes: list[int] = []
    in_excluded_section = False
    for idx, line in enumerate(lines):
        if match := H2_RE.match(line):
            heading = match.group(1).strip()
            in_excluded_section = heading in excluded_h2s
            continue
        if in_excluded_section:
            continue
        if _checkbox_text(line) == target_text:
            indexes.append(idx)
    return indexes


def sync_gtd_checkbox_line(
    gtd_path: Path,
    line: str,
    excluded_h2s: set[str],
    *,
    dry_run: bool = False,
) -> SyncResult:
    target = parse_checkbox_line(line)
    if target is None:
        return SyncResult(matched=0, changed=0, status="not-checkbox")
    if not gtd_path.exists():
        return SyncResult(matched=0, changed=0, status="missing-gtd")

    text = gtd_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    indexes = _candidate_indexes(lines, target.text, excluded_h2s)
    if not indexes:
        return SyncResult(matched=0, changed=0, status="no-match")
    if len(indexes) > 1:
        return SyncResult(matched=len(indexes), changed=0, status="ambiguous")

    idx = indexes[0]
    updated = _replace_checkbox_state(lines[idx], target.checked)
    if updated == lines[idx]:
        return SyncResult(matched=1, changed=0, status="already-synced")

    if not dry_run:
        lines[idx] = updated
        trailing_newline = "\n" if text.endswith("\n") else ""
        gtd_path.write_text("\n".join(lines) + trailing_newline, encoding="utf-8")
    return SyncResult(matched=1, changed=1, status="updated")


def parse_args(cfg: AgendaConfig) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync the checkbox state from one journal todo line to the matching "
            "line in gtd.md, ignoring leading whitespace and current checkbox state."
        )
    )
    parser.add_argument(
        "--line",
        required=True,
        help="The full markdown checkbox line after toggling.",
    )
    parser.add_argument(
        "--gtd",
        default=str(cfg.gtd_path) if cfg.gtd_path else None,
        help=(
            "Path to gtd.md "
            f"(default: {cfg.gtd_path if cfg.gtd_path else 'set agenda.gtd_path in config'})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without writing gtd.md.",
    )
    return parser.parse_args()


def main() -> int:
    cfg = load_config()
    args = parse_args(cfg)
    if not args.gtd:
        print(
            "No GTD path provided. Pass --gtd or set agenda.gtd_path in "
            "~/.config/hugin/agenda.yaml.",
            file=sys.stderr,
        )
        return 2

    result = sync_gtd_checkbox_line(
        Path(args.gtd).expanduser(),
        args.line,
        excluded_section_headings(cfg),
        dry_run=args.dry_run,
    )
    if result.status == "updated" and args.dry_run:
        print("[dry-run] Would sync 1 GTD checkbox.")
    elif result.status == "updated":
        print("Synced 1 GTD checkbox.")
    elif result.status == "already-synced":
        print("GTD checkbox already had that state.")
    elif result.status == "ambiguous":
        print(
            f"Found {result.matched} matching GTD checkbox lines; not syncing ambiguously.",
            file=sys.stderr,
        )
        return 3
    elif result.status == "missing-gtd":
        print(f"GTD file not found: {args.gtd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Rotate the daily journal file at year boundaries.

Archives journal.md to journal_<year>.md, removes that year's entries from the
live file, and updates the year heading. Defaults to the live `journal_path`
configured in hugin.yaml / agenda.yaml.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

from .config import load_config


def _parse_args(default_journal: Path | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Archive journal.md to journal_<year>.md, remove that year's entries, "
            "and update the year heading."
        )
    )
    parser.add_argument(
        "--journal",
        default=str(default_journal) if default_journal else None,
        help=(
            "Path to journal.md "
            f"(default: {default_journal if default_journal else 'set journal_path in config'})"
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Year to archive/remove (default: current year - 1)",
    )
    parser.add_argument(
        "--archive",
        default=None,
        help="Archive file path (default: journal_<year>.md in same dir)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing archive file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without writing files",
    )
    return parser.parse_args()


def _remove_year_entries(
    lines: list[str], year: int, start_from_heading: bool = True
) -> tuple[list[str], int]:
    date_re = re.compile(rf"^##\s+<?{year}-")
    new_lines: list[str] = []
    removed_entries = 0
    in_skip = False
    in_logg = not start_from_heading
    year_heading_re = re.compile(rf"^#\s+{year}\s*$")

    for line in lines:
        if start_from_heading and not in_logg:
            new_lines.append(line)
            if year_heading_re.match(line):
                in_logg = True
            continue

        if in_skip:
            if line.startswith("## "):
                if date_re.match(line):
                    removed_entries += 1
                    continue
                in_skip = False
                new_lines.append(line)
            continue

        if date_re.match(line):
            in_skip = True
            removed_entries += 1
            continue

        new_lines.append(line)

    return new_lines, removed_entries


def _update_year_heading(lines: list[str], old_year: int, new_year: int) -> bool:
    heading_re = re.compile(rf"^#\s+{old_year}\s*$")
    for idx, line in enumerate(lines):
        if heading_re.match(line):
            lines[idx] = f"# {new_year}\n" if line.endswith("\n") else f"# {new_year}"
            return True
    return False


def _update_journal_heading(lines: list[str], old_year: int, new_year: int) -> bool:
    journal_re = re.compile(rf"^#\s+Journal\s+{old_year}\s*$")
    for idx, line in enumerate(lines):
        if journal_re.match(line):
            lines[idx] = (
                f"# Journal {new_year}\n" if line.endswith("\n") else f"# Journal {new_year}"
            )
            return True
    return False


def main() -> int:
    cfg = load_config()
    args = _parse_args(cfg.journal_path)
    if not args.journal:
        print(
            "No journal path provided. Pass --journal or set journal_path in "
            "~/.config/hugin/hugin.yaml.",
            file=sys.stderr,
        )
        return 2

    journal_path = Path(args.journal).expanduser()
    if not journal_path.exists():
        print(f"Journal not found: {journal_path}", file=sys.stderr)
        return 2

    current_year = dt.date.today().year
    target_year = args.year if args.year is not None else current_year - 1
    archive_path = (
        Path(args.archive).expanduser()
        if args.archive
        else journal_path.with_name(f"journal_{target_year}.md")
    )

    text = journal_path.read_text(encoding="utf-8")
    if archive_path.exists() and not args.force:
        print(f"Archive already exists: {archive_path}", file=sys.stderr)
        return 3

    lines = text.splitlines(keepends=True)
    new_lines, removed_entries = _remove_year_entries(lines, target_year)
    journal_heading_updated = _update_journal_heading(
        new_lines, target_year, current_year
    )
    year_heading_updated = _update_year_heading(new_lines, target_year, current_year)

    if args.dry_run:
        print(f"[dry-run] Archive: {archive_path}")
        print(f"[dry-run] Remove entries for year: {target_year}")
        print(f"[dry-run] Removed entries: {removed_entries}")
        print(f"[dry-run] Journal heading updated: {journal_heading_updated}")
        print(f"[dry-run] Year heading updated: {year_heading_updated}")
        return 0

    archive_path.write_text(text, encoding="utf-8")
    journal_path.write_text("".join(new_lines), encoding="utf-8")

    print(f"Archived to: {archive_path}")
    print(f"Removed entries for year: {target_year} ({removed_entries} entries)")
    print(f"Journal heading updated: {journal_heading_updated}")
    print(f"Year heading updated: {year_heading_updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Rotate the live journal file into a dated archive.

Archives journal.md to arkiv/journal_yymmdd-yymmdd.md, using the inclusive
date range of the journal entries. Defaults to the live
`journal_path` configured in hugin.yaml / agenda.yaml.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

from .config import load_config


def _parse_args(default_journal: Path | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Archive journal.md to arkiv/journal_yymmdd-yymmdd.md, based on "
            "the earliest and latest dated entries."
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
        "--archive",
        default=None,
        help=(
            "Archive file path "
            "(default: arkiv/journal_yymmdd-yymmdd.md next to journal.md)"
        ),
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
    parser.add_argument(
        "--open-archive",
        action="store_true",
        help="Open the archive in Obsidian after rotating",
    )
    return parser.parse_args()


ENTRY_DATE_RE = re.compile(r"^##\s+<?(\d{4}-\d{2}-\d{2})(?:\b|[> ])")


def _entry_dates(text: str) -> list[str]:
    return [
        match.group(1)
        for line in text.splitlines()
        if (match := ENTRY_DATE_RE.match(line))
    ]


def _default_archive_path(journal_path: Path, start_date: str, end_date: str) -> Path:
    start = start_date[2:].replace("-", "")
    end = end_date[2:].replace("-", "")
    return journal_path.parent / "arkiv" / f"journal_{start}-{end}.md"


def _fresh_journal_text(year: int) -> str:
    return f"# Journal {year}\n\n"


def _obsidian_open_uri(path: Path, pane_type: str = "tab") -> str:
    query = urlencode({"path": str(path.resolve()), "paneType": pane_type})
    return f"obsidian://open?{query}"


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

    text = journal_path.read_text(encoding="utf-8")
    dates = _entry_dates(text)
    if not dates:
        print(
            "No journal entries found. Expected dated headings like "
            "'## 2026-05-04' or '## <2026-05-04 ...>'.",
            file=sys.stderr,
        )
        return 4

    start_date = min(dates)
    end_date = max(dates)
    archive_path = (
        Path(args.archive).expanduser()
        if args.archive
        else _default_archive_path(journal_path, start_date, end_date)
    )

    if archive_path.exists() and not args.force:
        print(f"Archive already exists: {archive_path}", file=sys.stderr)
        return 3

    if args.dry_run:
        print(f"[dry-run] Archive: {archive_path}")
        print(f"[dry-run] Date range: {start_date} to {end_date}")
        print(f"[dry-run] Entries: {len(dates)}")
        print(f"[dry-run] Reset journal: {journal_path}")
        print(f"[dry-run] New journal heading: # Journal {dt.date.today().year}")
        if args.open_archive:
            print(f"[dry-run] Open archive URI: {_obsidian_open_uri(archive_path)}")
        return 0

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(text, encoding="utf-8")
    journal_path.write_text(_fresh_journal_text(dt.date.today().year), encoding="utf-8")

    print(f"Archived to: {archive_path}")
    print(f"Entry dates: {start_date} to {end_date} ({len(dates)} entries)")
    print(f"Reset journal: {journal_path}")
    if args.open_archive:
        archive_uri = _obsidian_open_uri(archive_path)
        if webbrowser.open(archive_uri):
            print(f"Opened archive in Obsidian: {archive_uri}")
        else:
            print(f"Could not open archive in Obsidian: {archive_uri}", file=sys.stderr)
            return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

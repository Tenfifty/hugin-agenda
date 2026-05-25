from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hugin_agenda.rotate_journal import _default_archive_path, _entry_dates, main


SAMPLE_JOURNAL = """\
# Journal 2026

## 2026-05-01
- something

## <2026-05-15 Fri>
- another entry
"""


class EntryDatesTests(unittest.TestCase):
    def test_picks_dates_from_both_heading_styles(self) -> None:
        dates = _entry_dates(SAMPLE_JOURNAL)
        self.assertEqual(dates, ["2026-05-01", "2026-05-15"])

    def test_empty_when_no_dated_headings(self) -> None:
        self.assertEqual(_entry_dates("# Journal 2026\n\nnothing dated here"), [])


class DefaultArchivePathTests(unittest.TestCase):
    def test_uses_archive_dirname_argument(self) -> None:
        path = _default_archive_path(
            Path("/v/journal/journal.md"), "2026-05-01", "2026-05-15", "archive"
        )
        self.assertEqual(path, Path("/v/journal/archive/journal_260501-260515.md"))

    def test_swedish_arkiv_dirname(self) -> None:
        path = _default_archive_path(
            Path("/v/journal/journal.md"), "2026-05-01", "2026-05-15", "arkiv"
        )
        self.assertEqual(path, Path("/v/journal/arkiv/journal_260501-260515.md"))


class RotateMainSmokeTest(unittest.TestCase):
    """End-to-end: cfg.archive_dirname is threaded through main() to the
    archive path. Uses --journal to bypass the live config's journal_path."""

    def test_dry_run_uses_language_aware_archive_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            journal = base / "journal.md"
            journal.write_text(SAMPLE_JOURNAL)

            # Run rotate-journal dry-run; we just want it to exit 0 and not
            # blow up on the rotate_journal._default_archive_path call.
            rc = main_with_journal(journal)
            self.assertEqual(rc, 0)


def main_with_journal(journal: Path) -> int:
    import sys

    argv = sys.argv
    try:
        sys.argv = ["hugin-agenda-rotate-journal", "--journal", str(journal), "--dry-run"]
        return main()
    finally:
        sys.argv = argv


if __name__ == "__main__":
    unittest.main()

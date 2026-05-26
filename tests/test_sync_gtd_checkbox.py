from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hugin_agenda.sync_gtd_checkbox import (
    parse_checkbox_line,
    sync_gtd_checkbox_line,
)


EXCLUDED = {"Additions", "Removals", "Tillägg", "Borttagningar"}


class CheckboxLineTests(unittest.TestCase):
    def test_parses_checked_line_ignoring_indent(self) -> None:
        parsed = parse_checkbox_line("\t- [x] Spegla GTD-checks")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertTrue(parsed.checked)
        self.assertEqual(parsed.text, "Spegla GTD-checks")

    def test_non_checkbox_returns_none(self) -> None:
        self.assertIsNone(parse_checkbox_line("- not a checkbox"))


class SyncGtdCheckboxTests(unittest.TestCase):
    def _write_gtd(self, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        tmp.write(body)
        tmp.close()
        return Path(tmp.name)

    def test_updates_matching_line_ignoring_indent_and_checkbox_state(self) -> None:
        path = self._write_gtd(
            """\
## Vecka
### Tisdag
- [ ] Agendahugin
\t- [ ] Spegla GTD-checks
"""
        )

        result = sync_gtd_checkbox_line(
            path, "\t- [x] Spegla GTD-checks", EXCLUDED
        )

        self.assertEqual(result.status, "updated")
        self.assertIn("\t- [x] Spegla GTD-checks", path.read_text(encoding="utf-8"))

    def test_unchecks_matching_line(self) -> None:
        path = self._write_gtd("- [x] Svara Victor\n")

        result = sync_gtd_checkbox_line(path, "- [ ] Svara Victor", EXCLUDED)

        self.assertEqual(result.status, "updated")
        self.assertEqual(path.read_text(encoding="utf-8"), "- [ ] Svara Victor\n")

    def test_ignores_date_rule_overlay_sections(self) -> None:
        path = self._write_gtd(
            """\
## Vecka
### Tisdag
- [ ] Städa, 30m
## Tillägg
- [ ] Städa, 30m `2026-05-26`
"""
        )

        result = sync_gtd_checkbox_line(path, "- [x] Städa, 30m", EXCLUDED)

        self.assertEqual(result.status, "updated")
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            """\
## Vecka
### Tisdag
- [x] Städa, 30m
## Tillägg
- [ ] Städa, 30m `2026-05-26`
""",
        )

    def test_no_match_is_noop(self) -> None:
        path = self._write_gtd("- [ ] Other\n")

        result = sync_gtd_checkbox_line(path, "- [x] Missing", EXCLUDED)

        self.assertEqual(result.status, "no-match")
        self.assertEqual(path.read_text(encoding="utf-8"), "- [ ] Other\n")

    def test_multiple_matches_are_ambiguous_and_not_written(self) -> None:
        path = self._write_gtd("- [ ] Duplicate\n- [ ] Duplicate\n")

        result = sync_gtd_checkbox_line(path, "- [x] Duplicate", EXCLUDED)

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(path.read_text(encoding="utf-8"), "- [ ] Duplicate\n- [ ] Duplicate\n")


if __name__ == "__main__":
    unittest.main()

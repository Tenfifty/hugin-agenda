from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from hugin_agenda.overlays import (
    OverlayError,
    apply_removals,
    parse_overlays,
    parse_rule,
    active_additions,
    active_removals,
)


class RuleParsingTests(unittest.TestCase):
    def test_iso_date_shorthand(self) -> None:
        rule = parse_rule("2026-06-17")
        self.assertTrue(rule.matches(date(2026, 6, 17)))
        self.assertFalse(rule.matches(date(2026, 6, 18)))

    def test_iso_range_shorthand(self) -> None:
        rule = parse_rule("2026-07-01..2026-07-21")
        self.assertTrue(rule.matches(date(2026, 7, 1)))
        self.assertTrue(rule.matches(date(2026, 7, 21)))
        self.assertTrue(rule.matches(date(2026, 7, 10)))
        self.assertFalse(rule.matches(date(2026, 6, 30)))
        self.assertFalse(rule.matches(date(2026, 7, 22)))

    def test_yaml_flow(self) -> None:
        # Biweekly Wednesday starting 2026-06-17
        rule = parse_rule("{weekdays: [wed], every_n_days_from: [2026-06-17, 14]}")
        self.assertTrue(rule.matches(date(2026, 6, 17)))
        self.assertFalse(rule.matches(date(2026, 6, 24)))
        self.assertTrue(rule.matches(date(2026, 7, 1)))

    def test_unknown_syntax_raises(self) -> None:
        with self.assertRaises(OverlayError):
            parse_rule("not-a-date")

    def test_empty_raises(self) -> None:
        with self.assertRaises(OverlayError):
            parse_rule("   ")


class MatcherTests(unittest.TestCase):
    def test_weekdays_single_and_list(self) -> None:
        self.assertTrue(parse_rule("{weekdays: wed}").matches(date(2026, 6, 17)))
        self.assertTrue(parse_rule("{weekdays: [mon, thu]}").matches(date(2026, 6, 18)))
        self.assertFalse(parse_rule("{weekdays: [mon, thu]}").matches(date(2026, 6, 17)))

    def test_months(self) -> None:
        rule = parse_rule("{months: [6, 7, 8]}")
        self.assertTrue(rule.matches(date(2026, 7, 1)))
        self.assertFalse(rule.matches(date(2026, 5, 31)))

    def test_day_of_month(self) -> None:
        rule = parse_rule("{day_of_month: [1, 15]}")
        self.assertTrue(rule.matches(date(2026, 6, 1)))
        self.assertTrue(rule.matches(date(2026, 6, 15)))
        self.assertFalse(rule.matches(date(2026, 6, 2)))

    def test_every_n_days_from(self) -> None:
        rule = parse_rule("{every_n_days_from: [2026-01-07, 28]}")
        self.assertTrue(rule.matches(date(2026, 1, 7)))
        self.assertTrue(rule.matches(date(2026, 2, 4)))   # +28
        self.assertTrue(rule.matches(date(2026, 3, 4)))   # +56
        self.assertFalse(rule.matches(date(2026, 1, 8)))
        # Before anchor → no match (avoid wrap-around)
        self.assertFalse(rule.matches(date(2026, 1, 6)))

    def test_nth_weekday(self) -> None:
        # First Monday of June 2026 = 2026-06-01
        self.assertTrue(parse_rule("{nth_weekday: [1, mon]}").matches(date(2026, 6, 1)))
        self.assertFalse(parse_rule("{nth_weekday: [1, mon]}").matches(date(2026, 6, 8)))
        # Last Friday of June 2026 = 2026-06-26
        self.assertTrue(parse_rule("{nth_weekday: [-1, fri]}").matches(date(2026, 6, 26)))
        self.assertFalse(parse_rule("{nth_weekday: [-1, fri]}").matches(date(2026, 6, 19)))
        # Second-to-last Friday of June 2026 = 2026-06-19
        self.assertTrue(parse_rule("{nth_weekday: [-2, fri]}").matches(date(2026, 6, 19)))
        self.assertFalse(parse_rule("{nth_weekday: [-2, fri]}").matches(date(2026, 6, 26)))

    def test_day_of_month_negative(self) -> None:
        # 2026-06-30 is the last day of June (30 days)
        self.assertTrue(parse_rule("{day_of_month: [-1]}").matches(date(2026, 6, 30)))
        self.assertFalse(parse_rule("{day_of_month: [-1]}").matches(date(2026, 6, 29)))
        # 2026-02 has 28 days → -1 == 28
        self.assertTrue(parse_rule("{day_of_month: [-1]}").matches(date(2026, 2, 28)))
        # Mixed positive and negative
        rule = parse_rule("{day_of_month: [1, -1]}")
        self.assertTrue(rule.matches(date(2026, 6, 1)))
        self.assertTrue(rule.matches(date(2026, 6, 30)))

    def test_not(self) -> None:
        rule = parse_rule("{weekdays: wed, not: {dates: [2026-06-24]}}")
        self.assertTrue(rule.matches(date(2026, 6, 17)))
        self.assertFalse(rule.matches(date(2026, 6, 24)))

    def test_combination_is_and(self) -> None:
        rule = parse_rule("{weekdays: [wed], months: [6]}")
        self.assertTrue(rule.matches(date(2026, 6, 17)))
        self.assertFalse(rule.matches(date(2026, 7, 1)))  # Wed but July


class GtdParsingTests(unittest.TestCase):
    def _write_gtd(self, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        tmp.write(body)
        tmp.close()
        return Path(tmp.name)

    def test_missing_file_returns_empty(self) -> None:
        adds, rems = parse_overlays(Path("/nonexistent/path/gtd.md"))
        self.assertEqual(adds, [])
        self.assertEqual(rems, [])

    def test_missing_sections_silent(self) -> None:
        path = self._write_gtd("# Notes\nNothing here.\n")
        adds, rems = parse_overlays(path)
        self.assertEqual(adds, [])
        self.assertEqual(rems, [])

    def test_parses_additions_and_removals(self) -> None:
        body = """\
# Top
## Additions
- [ ] Dentist 14:00 `2026-06-17`
- [ ] Take out glass `{weekdays: [wed], every_n_days_from: [2026-01-07, 28]}`
- not a checkbox line (ignored)

## Removals
- Clockify `2026-07-01..2026-07-21`
- Standup `2026-07-01..2026-07-21`

## Other
- ignored
"""
        path = self._write_gtd(body)
        adds, rems = parse_overlays(path)
        self.assertEqual(len(adds), 2)
        self.assertEqual(adds[0].text, "- [ ] Dentist 14:00")
        self.assertTrue(adds[0].rule.matches(date(2026, 6, 17)))
        self.assertEqual(len(rems), 2)
        self.assertEqual(rems[0].pattern, "Clockify")

    def test_section_ends_at_next_h2(self) -> None:
        body = """\
## Additions
- [ ] Inside `2026-06-17`
## Other
- [ ] Outside `2026-06-17`
"""
        path = self._write_gtd(body)
        adds, _ = parse_overlays(path)
        self.assertEqual(len(adds), 1)
        self.assertEqual(adds[0].text, "- [ ] Inside")

    def test_named_sections_inherit_h3_rule(self) -> None:
        from datetime import date
        body = """\
## Additions
- [ ] Dentist `2026-06-17`
### Kontor `{weekdays: [mon, thu]}`
- [ ] Städa, 20m
- [ ] Snabblunch
### Helg `{weekdays: [sat, sun]}`
- [ ] Städa, 30m
## Removals
### Kontor `{weekdays: [mon, thu]}`
- Bastu
- Städa, 30m
"""
        path = self._write_gtd(body)
        adds, rems = parse_overlays(path)
        # Default-section addition keeps its inline rule
        self.assertEqual(adds[0].text, "- [ ] Dentist")
        self.assertIsNone(adds[0].section)
        # Named sections inherit
        kontor = [a for a in adds if a.section == "Kontor"]
        helg = [a for a in adds if a.section == "Helg"]
        self.assertEqual(len(kontor), 2)
        self.assertEqual(len(helg), 1)
        # Kontor's section rule matches Monday but not Saturday
        self.assertTrue(kontor[0].rule.matches(date(2026, 5, 25)))  # Mon
        self.assertFalse(kontor[0].rule.matches(date(2026, 5, 30)))  # Sat
        # Removals also got the section
        self.assertEqual([r.section for r in rems], ["Kontor", "Kontor"])
        self.assertEqual([r.pattern for r in rems], ["Bastu", "Städa, 30m"])

    def test_h3_without_rule_skips_items(self) -> None:
        body = """\
## Additions
### Notes (no rule, just a comment heading)
- [ ] This should not fire
"""
        path = self._write_gtd(body)
        adds, _ = parse_overlays(path)
        self.assertEqual(adds, [])

    def test_list_section_names(self) -> None:
        from hugin_agenda.overlays import list_section_names
        body = """\
## Additions
### Kontor `{weekdays: [mon, thu]}`
- [ ] x
### Helg `{weekdays: [sat, sun]}`
- [ ] y
## Removals
### Kontor `{weekdays: [mon, thu]}`
- Bastu
"""
        path = self._write_gtd(body)
        self.assertEqual(list_section_names(path), ["Kontor", "Helg"])

    def test_override_forces_section(self) -> None:
        from datetime import date
        body = """\
## Additions
### Kontor `{weekdays: [mon, thu]}`
- [ ] Snabblunch
"""
        path = self._write_gtd(body)
        adds, _ = parse_overlays(path)
        # Wednesday — Kontor's date rule does NOT match
        self.assertEqual(active_additions(adds, date(2026, 5, 27)), [])
        # With override, fires anyway
        active = active_additions(adds, date(2026, 5, 27), override="Kontor")
        self.assertEqual(len(active), 1)

    def test_suppress_named_skips_section_items(self) -> None:
        from datetime import date
        body = """\
## Additions
- [ ] Dentist `2026-05-25`
### Kontor `{weekdays: [mon, thu]}`
- [ ] Snabblunch
"""
        path = self._write_gtd(body)
        adds, _ = parse_overlays(path)
        # Monday with suppress_named: only the per-line addition fires
        active = active_additions(adds, date(2026, 5, 25), suppress_named=True)
        self.assertEqual([a.text for a in active], ["- [ ] Dentist"])


class ActiveAndApplyTests(unittest.TestCase):
    def test_active_additions_filters_by_date(self) -> None:
        from hugin_agenda.overlays import Addition, Rule

        adds = [
            Addition("- [ ] A", parse_rule("2026-06-17")),
            Addition("- [ ] B", parse_rule("2026-06-18")),
        ]
        active = active_additions(adds, date(2026, 6, 17))
        self.assertEqual([a.text for a in active], ["- [ ] A"])

    def test_apply_removals_substring_match(self) -> None:
        from hugin_agenda.overlays import Removal

        lines = [
            "- [ ] Clockify",
            "- [ ] Inbox Zero",
            "- [ ] Weekly review",
        ]
        rems = [Removal("Clockify", parse_rule("2026-07-10"))]
        active = active_removals(rems, date(2026, 7, 10))
        out = apply_removals(lines, active)
        self.assertEqual(out, ["- [ ] Inbox Zero", "- [ ] Weekly review"])

    def test_apply_removals_inactive_is_noop(self) -> None:
        from hugin_agenda.overlays import Removal

        lines = ["- [ ] Clockify"]
        rems = [Removal("Clockify", parse_rule("2026-07-10"))]
        active = active_removals(rems, date(2026, 6, 1))
        self.assertEqual(apply_removals(lines, active), lines)


class RenderIntegrationTests(unittest.TestCase):
    def test_addition_appears_and_removal_strips(self) -> None:
        from hugin_agenda.agenda import GtdTaskBlock, render_agenda
        from hugin_agenda.config import AgendaConfig
        from hugin_agenda.overlays import Removal

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "agenda_base.md").write_text(
                "## YYYY-MM-DD\n### Agenda\n- [ ] Template item\n- [ ] Agenda 2\n",
                encoding="utf-8",
            )
            cfg = AgendaConfig.from_merged({"language": "en"})
            cfg.templates_dir = tmp_path

            tasks = [GtdTaskBlock(lines=["- [ ] Weekly task"], duration_slots=1)]
            extra = [GtdTaskBlock(lines=["- [ ] Dentist"], duration_slots=1)]
            rems = [Removal("Template item", parse_rule("2026-06-17"))]

            out = render_agenda(
                cfg=cfg,
                target_date=date(2026, 6, 17),
                template_name="base",
                events=[],
                tasks=tasks + extra,
                removals=active_removals(rems, date(2026, 6, 17)),
            )
            self.assertIn("Weekly task", out)
            self.assertIn("Dentist", out)
            self.assertNotIn("Template item", out)


class InsertionMarkerTests(unittest.TestCase):
    def test_blank_line_after_list_item_is_marker(self) -> None:
        from hugin_agenda.agenda import find_agenda_insertion_index

        lines = [
            "## Date",
            ":-) ",
            "",                # blank between header text — NOT the marker
            "### Agenda",
            "- [ ] Template item",
            "",                # marker: blank after list item
            "- [ ] Städa",
            "- [ ] Agenda 2",
        ]
        self.assertEqual(find_agenda_insertion_index(lines), 5)

    def test_no_marker_appends_at_end(self) -> None:
        from hugin_agenda.agenda import find_agenda_insertion_index

        lines = [
            "## Date",
            "### Agenda",
            "- [ ] Template item",
            "- [ ] Agenda 2",
        ]
        self.assertEqual(find_agenda_insertion_index(lines), 4)


if __name__ == "__main__":
    unittest.main()

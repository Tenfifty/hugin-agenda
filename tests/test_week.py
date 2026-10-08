from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from hugin_agenda.overlays import parse_overlays
from hugin_agenda.week import (
    booked_hours,
    clashing,
    item_text,
    overdue_additions,
    plan_week,
    render_week,
)


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute)


MONDAY = date(2026, 10, 12)

GTD = """\
# GTD
## Tillägg
- [ ] Lufta elementen `2026-10-15`
- [x] Redan gjord `2026-10-14`
- [ ] Gammal påminnelse `2026-09-30`
- [x] Gammal men gjord `2026-09-13`
- [ ] Vattna `2026-10-10..2026-10-13`
- [ ] Återvinn glas `{every_n_days_from: [2026-10-13, 28]}`
### Kontor `{weekdays: [mon, thu]}`
- [ ] Fika *~{15:00 - 15:30}*
## Borttagningar
### Kontor `{weekdays: [mon, thu]}`
- [ ] Bastu
"""

TEMPLATE = [
    "## <date>",
    ":-) ",
    "",
    "### Agenda",
    "- [ ] Stretch",
    "- [ ] Bastu",
    "",
]


class WeekTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        gtd = Path(self.tmp.name) / "gtd.md"
        gtd.write_text(GTD, encoding="utf-8")
        self.additions, self.removals = parse_overlays(gtd, "Tillägg", "Borttagningar")


class ItemTextTests(unittest.TestCase):
    def test_strips_checkbox_and_moves_time_marker(self) -> None:
        self.assertEqual(item_text("- [ ] Fika *~{15:00 - 15:30}*"), "Fika 15:00–15:30")

    def test_wikilink_shows_label(self) -> None:
        self.assertEqual(
            item_text("- [ ] Köp klocka [[gtd-research/2026-06/beslut|Beslut]]"),
            "Köp klocka Beslut",
        )
        self.assertEqual(item_text("- [x] Läs [[health]]"), "Läs health")


class CheckedAdditionTests(WeekTestCase):
    def test_checked_flag_parsed(self) -> None:
        by_text = {item_text(a.text): a.checked for a in self.additions}
        self.assertTrue(by_text["Redan gjord"])
        self.assertFalse(by_text["Lufta elementen"])


class PlanWeekTests(WeekTestCase):
    def plans(self):
        return plan_week(MONDAY, {}, TEMPLATE, self.additions, self.removals)

    def test_seven_days_from_start(self) -> None:
        plans = self.plans()
        self.assertEqual([p.day for p in plans][0], MONDAY)
        self.assertEqual(len(plans), 7)

    def test_dated_on_its_day_and_checked_skipped(self) -> None:
        plans = self.plans()
        self.assertEqual(plans[3].dated, ["Lufta elementen"])
        self.assertEqual(plans[2].dated, [])

    def test_routines_follow_rules_and_removals(self) -> None:
        plans = self.plans()
        self.assertEqual(plans[0].routines, ["Stretch", "Vattna", "Fika 15:00–15:30"])
        self.assertEqual(plans[1].routines, ["Stretch", "Bastu", "Vattna", "Återvinn glas"])

    def test_date_range_is_a_routine_not_dated(self) -> None:
        plans = self.plans()
        self.assertIn("Vattna", plans[0].routines)
        self.assertEqual(plans[0].dated, [])
        self.assertNotIn("Vattna", plans[2].routines)

    def test_overdue_lists_only_unchecked_past_items(self) -> None:
        self.assertEqual(
            overdue_additions(self.additions, MONDAY),
            [(date(2026, 9, 30), "Gammal påminnelse")],
        )


class EventTests(unittest.TestCase):
    def test_booked_hours_counts_overlap_once(self) -> None:
        events = [
            Event("Workshop", at(MONDAY, 9), at(MONDAY, 12)),
            Event("Checkin", at(MONDAY, 10, 30), at(MONDAY, 11, 30)),
            Event("Lunch", at(MONDAY, 13), at(MONDAY, 13, 30)),
            Event("Resa", at(MONDAY, 0), at(MONDAY, 23, 59), all_day=True),
        ]
        self.assertAlmostEqual(booked_hours(events, MONDAY), 3.5)

    def test_booked_hours_clips_to_the_day(self) -> None:
        events = [Event("Natt", at(MONDAY, 22), datetime(2026, 10, 13, 2))]
        self.assertAlmostEqual(booked_hours(events, MONDAY), 2.0)

    def test_clashing_marks_both_sides(self) -> None:
        events = [
            Event("A", at(MONDAY, 9), at(MONDAY, 12)),
            Event("B", at(MONDAY, 10), at(MONDAY, 11)),
            Event("C", at(MONDAY, 12), at(MONDAY, 13)),
        ]
        self.assertEqual(clashing(events), {0, 1})


class RenderTests(WeekTestCase):
    def test_swedish_overview(self) -> None:
        events = {
            MONDAY: [
                Event("Workshop", at(MONDAY, 9), at(MONDAY, 12)),
                Event("Checkin", at(MONDAY, 10, 30), at(MONDAY, 11, 30)),
            ]
        }
        plans = plan_week(MONDAY, events, TEMPLATE, self.additions, self.removals)
        text = render_week(plans, overdue_additions(self.additions, MONDAY), "sv")
        self.assertIn("# Vecka 42 · 12/10–18/10", text)
        self.assertIn("**Försenat**\n- Gammal påminnelse (30/9)", text)
        self.assertIn("**mån 12/10** · 3 h bokat", text)
        self.assertIn("- 09:00–12:00 Workshop ⚠️ krock", text)
        self.assertIn("**tor 15/10**\n- 📌 Lufta elementen", text)
        self.assertIn("| Fika 15:00–15:30 | ● |  |  | ● |  |  |  |", text)
        self.assertIn("*Varje dag:* Stretch", text)

    def test_english_labels(self) -> None:
        plans = plan_week(MONDAY, {}, TEMPLATE, self.additions, self.removals)
        text = render_week(plans, [], "en")
        self.assertIn("# Week 42 · Oct 12–Oct 18", text)
        self.assertIn("**Mon Oct 12**", text)
        self.assertIn("*Every day:* Stretch", text)


if __name__ == "__main__":
    unittest.main()

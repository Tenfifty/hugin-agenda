from __future__ import annotations

import unittest
from pathlib import Path

from hugin_agenda.config import (
    PACKAGED_TEMPLATES_DIR,
    WEEKDAYS_BY_LANGUAGE,
    AgendaConfig,
)


class AgendaConfigTests(unittest.TestCase):
    def test_defaults_when_no_agenda_section(self) -> None:
        cfg = AgendaConfig.from_merged({"language": "en"})
        self.assertEqual(cfg.language, "en")
        self.assertEqual(cfg.calendar_id, "primary")
        self.assertEqual(cfg.task_slot_minutes, 30)
        self.assertEqual(cfg.day_start_hour, 9)
        self.assertEqual(cfg.templates_dir, PACKAGED_TEMPLATES_DIR)
        self.assertIsNone(cfg.gtd_path)

    def test_agenda_section_overrides(self) -> None:
        cfg = AgendaConfig.from_merged({
            "language": "sv",
            "agenda": {
                "calendar_id": "work@example.com",
                "task_slot_minutes": 15,
                "day_start_hour": 8,
                "gtd_path": "/tmp/gtd.md",
                "template_map": {"0": "weekday", "5": "weekend", "6": "weekend"},
            },
        })
        self.assertEqual(cfg.language, "sv")
        self.assertEqual(cfg.calendar_id, "work@example.com")
        self.assertEqual(cfg.task_slot_minutes, 15)
        self.assertEqual(cfg.day_start_hour, 8)
        self.assertEqual(cfg.gtd_path, Path("/tmp/gtd.md"))
        # template_map keys are coerced to int even when YAML gives strings
        self.assertEqual(cfg.template_map[0], "weekday")
        self.assertEqual(cfg.template_map[5], "weekend")

    def test_resolved_weekday_names_swedish(self) -> None:
        cfg = AgendaConfig.from_merged({"language": "sv"})
        self.assertEqual(cfg.resolved_weekday_names(), WEEKDAYS_BY_LANGUAGE["sv"])
        self.assertEqual(cfg.resolved_weekday_names()[0], "Måndag")

    def test_resolved_weekday_names_english_default(self) -> None:
        cfg = AgendaConfig.from_merged({})
        self.assertEqual(cfg.resolved_weekday_names()[0], "Monday")

    def test_weekday_names_override_wins(self) -> None:
        cfg = AgendaConfig.from_merged({
            "language": "sv",
            "agenda": {"weekday_names": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
        })
        self.assertEqual(cfg.resolved_weekday_names()[0], "Mon")


class SharedFieldsTests(unittest.TestCase):
    def test_archive_dirname_follows_language(self) -> None:
        self.assertEqual(AgendaConfig.from_merged({"language": "en"}).archive_dirname, "archive")
        self.assertEqual(AgendaConfig.from_merged({"language": "sv"}).archive_dirname, "arkiv")

    def test_explicit_archive_dirname_wins(self) -> None:
        cfg = AgendaConfig.from_merged({"language": "sv", "archive_dirname": "old"})
        self.assertEqual(cfg.archive_dirname, "old")


if __name__ == "__main__":
    unittest.main()

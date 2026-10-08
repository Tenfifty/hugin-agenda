from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hugin_agenda.config import AgendaConfig
from hugin_agenda.research import _swap_marker_on_disk, marker_needles

SLUG = "kop-hasselnotsbuske-260526-2208"


class MarkerNeedleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        vault = Path(self.tmp.name)
        self.gtd = vault / "gtd.md"
        self.cfg = AgendaConfig(gtd_path=self.gtd, research_dir=vault / "_hugin" / "utredningar")
        self.sidecar = vault / "_hugin" / "utredningar" / "2026-05" / f"{SLUG}.md"

    def swap(self, text: str) -> str:
        self.gtd.write_text(text, encoding="utf-8")
        _swap_marker_on_disk(self.gtd, marker_needles(self.cfg, self.sidecar), "✅")
        return self.gtd.read_text(encoding="utf-8")

    def test_full_path_link_gets_marker(self) -> None:
        line = f"- [ ] Köp buske [[_hugin/utredningar/2026-05/{SLUG}|Research]] 🔄\n"
        self.assertIn(f"{SLUG}|Research]] ✅", self.swap(line))

    def test_link_shortened_by_obsidian_gets_marker(self) -> None:
        line = f"- [ ] Köp buske [[{SLUG}|Research]] 🔄\n"
        self.assertEqual(self.swap(line), f"- [ ] Köp buske [[{SLUG}|Research]] ✅\n")

    def test_other_lines_are_left_alone(self) -> None:
        text = f"- [ ] Annat [[annan-slug-260526-2209|Research]] 🔄\n"
        self.assertEqual(self.swap(text), text)


if __name__ == "__main__":
    unittest.main()

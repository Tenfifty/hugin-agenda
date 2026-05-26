"""Configuration loading for Hugin Agenda.

Reads ~/.config/hugin/hugin.yaml + ~/.config/hugin/agenda.yaml via
:func:`hugin.config.load_tool`. Override the config dir with
``HUGIN_CONFIG_DIR``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from hugin.config import SharedConfig, load_tool


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGED_TEMPLATES_DIR = PACKAGE_DIR / "templates"


# Weekday name lookups for parsing GTD headings like "### Måndag" / "### Monday".
WEEKDAYS_BY_LANGUAGE: dict[str, list[str]] = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "sv": ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"],
}

# H2 headings that delimit the additions/removals overlay sections in gtd.md.
OVERLAY_HEADINGS_BY_LANGUAGE: dict[str, dict[str, str]] = {
    "en": {"additions": "Additions", "removals": "Removals"},
    "sv": {"additions": "Tillägg", "removals": "Borttagningar"},
}


def _opt_path(value: Any) -> Path | None:
    return Path(value).expanduser() if value else None


@dataclass
class AgendaConfig(SharedConfig):
    # Agenda-specific
    templates_dir: Path = PACKAGED_TEMPLATES_DIR
    gtd_path: Path | None = None
    calendar_id: str = "primary"
    task_slot_minutes: int = 30
    day_start_hour: int = 9

    # Template name (without "agenda_" prefix / ".md"). The resolved file is
    # <templates_dir>/agenda_<base_template>.md. Per-day variation is handled
    # via `## Additions` / `## Removals` in gtd.md.
    base_template: str = "base"

    # Weekday names used to find the right day in gtd.md. Defaults are
    # looked up from `language`; override here to force a specific list.
    weekday_names: list[str] | None = None

    # H2 headings of the overlay sections in gtd.md. Defaults follow
    # `language` (en: Additions/Removals; sv: Tillägg/Borttagningar).
    additions_heading: str | None = None
    removals_heading: str | None = None

    def resolved_weekday_names(self) -> list[str]:
        if self.weekday_names:
            return self.weekday_names
        return WEEKDAYS_BY_LANGUAGE.get(self.language, WEEKDAYS_BY_LANGUAGE["en"])

    def resolved_overlay_headings(self) -> tuple[str, str]:
        defaults = OVERLAY_HEADINGS_BY_LANGUAGE.get(
            self.language, OVERLAY_HEADINGS_BY_LANGUAGE["en"]
        )
        return (
            self.additions_heading or defaults["additions"],
            self.removals_heading or defaults["removals"],
        )

    @classmethod
    def from_merged(cls, merged: dict[str, Any]) -> "AgendaConfig":
        agenda = merged.get("agenda", {}) if isinstance(merged.get("agenda"), dict) else {}

        return cls(
            **SharedConfig.fields_from_merged(merged),
            templates_dir=_opt_path(agenda.get("templates_dir")) or PACKAGED_TEMPLATES_DIR,
            gtd_path=_opt_path(agenda.get("gtd_path")),
            calendar_id=agenda.get("calendar_id", "primary"),
            task_slot_minutes=int(agenda.get("task_slot_minutes", 30)),
            day_start_hour=int(agenda.get("day_start_hour", 9)),
            base_template=str(agenda.get("base_template", "base")),
            weekday_names=agenda.get("weekday_names"),
            additions_heading=agenda.get("additions_heading"),
            removals_heading=agenda.get("removals_heading"),
        )


@lru_cache(maxsize=1)
def load_config() -> AgendaConfig:
    return load_tool("agenda", AgendaConfig.from_merged)


def reset_config_cache() -> None:
    """For tests."""
    load_config.cache_clear()

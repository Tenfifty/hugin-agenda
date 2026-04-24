"""Configuration loading for Hugin Agenda.

Reads two YAML files and merges them (agenda.yaml overrides hugin.yaml):
- ~/.config/hugin/hugin.yaml   -- shared across all hugin-* tools
- ~/.config/hugin/agenda.yaml  -- agenda-specific

Environment variable HUGIN_CONFIG_DIR overrides the config directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGED_TEMPLATES_DIR = PACKAGE_DIR / "templates"


def _config_dir() -> Path:
    override = os.environ.get("HUGIN_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "hugin"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at top level")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


# Weekday name lookups for parsing GTD headings like "### Måndag" / "### Monday".
WEEKDAYS_BY_LANGUAGE: dict[str, list[str]] = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "sv": ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"],
}


@dataclass
class AgendaConfig:
    # Shared
    language: str = "en"
    user_name: str = ""
    vault_path: Path | None = None

    # Google Workspace CLI (shared with hugin-meetings)
    gws_bin: str = "gws"
    gws_config_dir: Path | None = None

    # Journal (shared with hugin-meetings)
    journal_path: Path | None = None

    # Agenda-specific
    templates_dir: Path = PACKAGED_TEMPLATES_DIR
    gtd_path: Path | None = None
    calendar_id: str = "primary"
    task_slot_minutes: int = 30
    day_start_hour: int = 9

    # weekday index (0=Mon..6=Sun) -> template name (without "agenda_" prefix / ".md")
    template_map: dict[int, str] = field(default_factory=lambda: {
        0: "weekday", 1: "weekday", 2: "weekday", 3: "weekday", 4: "weekday",
        5: "weekend", 6: "weekend",
    })

    # Weekday names used to find the right day in gtd.md. Defaults are
    # looked up from `language`; override here to force a specific list.
    weekday_names: list[str] | None = None

    # Raw merged dict for anything not explicitly modeled
    raw: dict[str, Any] = field(default_factory=dict)

    def resolved_weekday_names(self) -> list[str]:
        if self.weekday_names:
            return self.weekday_names
        return WEEKDAYS_BY_LANGUAGE.get(self.language, WEEKDAYS_BY_LANGUAGE["en"])


def _lookup(merged: dict[str, Any], agenda: dict[str, Any], key: str) -> Any:
    """Agenda-nested value wins; fall back to top-level shared."""
    if key in agenda:
        return agenda[key]
    return merged.get(key)


def _path_or(value: Any, default: Path | None) -> Path | None:
    if value:
        return Path(value).expanduser()
    return default


def _build(merged: dict[str, Any]) -> AgendaConfig:
    merged = _expand(merged)
    agenda = merged.get("agenda", {}) if isinstance(merged.get("agenda"), dict) else {}

    template_map_raw = agenda.get("template_map")
    if isinstance(template_map_raw, dict):
        template_map = {int(k): str(v) for k, v in template_map_raw.items()}
    else:
        template_map = AgendaConfig().template_map

    cfg = AgendaConfig(
        language=merged.get("language", "en"),
        user_name=merged.get("user_name", ""),
        vault_path=_path_or(merged.get("vault_path"), None),
        gws_bin=_lookup(merged, agenda, "gws_bin") or "gws",
        gws_config_dir=_path_or(_lookup(merged, agenda, "gws_config_dir"), None),
        journal_path=_path_or(_lookup(merged, agenda, "journal_path"), None),
        templates_dir=_path_or(agenda.get("templates_dir"), PACKAGED_TEMPLATES_DIR),
        gtd_path=_path_or(agenda.get("gtd_path"), None),
        calendar_id=agenda.get("calendar_id", "primary"),
        task_slot_minutes=int(agenda.get("task_slot_minutes", 30)),
        day_start_hour=int(agenda.get("day_start_hour", 9)),
        template_map=template_map,
        weekday_names=agenda.get("weekday_names"),
        raw=merged,
    )
    return cfg


@lru_cache(maxsize=1)
def load_config() -> AgendaConfig:
    cfg_dir = _config_dir()
    shared = _load_yaml(cfg_dir / "hugin.yaml")
    agenda = _load_yaml(cfg_dir / "agenda.yaml")
    merged = _deep_merge(shared, agenda)
    return _build(merged)


def reset_config_cache() -> None:
    """For tests."""
    load_config.cache_clear()

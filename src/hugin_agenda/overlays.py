"""Date-rule overlays parsed from gtd.md's `## Additions` / `## Removals`.

Each overlay line is `- [ ] text `rule`` (addition) or `- text `rule`` (removal),
where `rule` is one of:

- ``YYYY-MM-DD``                      → ``{dates: [<date>]}``
- ``YYYY-MM-DD..YYYY-MM-DD``          → ``{date_ranges: [[<start>, <end>]]}``
- ``{...}``                           → YAML flow mapping, parsed as-is

Supported matcher keys (all AND together; lists within a key OR):
``weekdays, months, day_of_month, nth_weekday, dates, date_ranges,
every_n_days_from, not``.

``day_of_month`` accepts 1..31 (forward) or -1..-31 (from end of month, so
-1 = last day). ``nth_weekday: [n, weekday]`` is 1-indexed: 1 = first
occurrence, -1 = last, -2 = second-to-last. For biweekly / quad-week
cadences use ``every_n_days_from: [<anchor>, <n>]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml


WEEKDAY_INDEX = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


class OverlayError(ValueError):
    pass


@dataclass
class Rule:
    raw: dict[str, Any] = field(default_factory=dict)

    def matches(self, target: date) -> bool:
        return _matches(self.raw, target)


@dataclass
class Addition:
    text: str
    rule: Rule
    section: str | None = None


@dataclass
class Removal:
    pattern: str
    rule: Rule
    section: str | None = None


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")


def parse_rule(raw: str) -> Rule:
    text = raw.strip()
    if not text:
        raise OverlayError("empty rule")

    if _ISO_DATE.match(text):
        return Rule({"dates": [date.fromisoformat(text)]})

    range_match = _ISO_RANGE.match(text)
    if range_match:
        start = date.fromisoformat(range_match.group(1))
        end = date.fromisoformat(range_match.group(2))
        return Rule({"date_ranges": [[start, end]]})

    if text.startswith("{"):
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise OverlayError(f"invalid YAML in rule {text!r}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise OverlayError(f"rule must be a mapping, got {type(parsed).__name__}: {text!r}")
        return Rule(parsed)

    raise OverlayError(
        f"unrecognized rule {text!r}: expected ISO date, ISO range, or {{yaml}} mapping"
    )


def _matches(rule: dict[str, Any], target: date) -> bool:
    for key, value in rule.items():
        if not _match_field(key, value, target):
            return False
    return True


def _match_field(key: str, value: Any, target: date) -> bool:
    if key == "weekdays":
        return target.weekday() in {_weekday(v) for v in _as_list(value)}
    if key == "months":
        return target.month in {int(v) for v in _as_list(value)}
    if key == "day_of_month":
        days = _month_days(target.year, target.month)
        return target.day in {_resolve_day(int(v), days) for v in _as_list(value)}
    if key == "nth_weekday":
        position, weekday = value
        return _matches_nth_weekday(target, position, weekday)
    if key == "dates":
        return target in {_as_date(v) for v in _as_list(value)}
    if key == "date_ranges":
        return any(_as_date(a) <= target <= _as_date(b) for a, b in value)
    if key == "every_n_days_from":
        anchor, n = value
        anchor = _as_date(anchor)
        delta = (target - anchor).days
        return delta >= 0 and delta % int(n) == 0
    if key == "not":
        if not isinstance(value, dict):
            raise OverlayError(f"'not' must be a mapping, got {type(value).__name__}")
        return not _matches(value, target)
    raise OverlayError(f"unknown matcher key: {key!r}")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _weekday(value: Any) -> int:
    if isinstance(value, int):
        return value
    key = str(value).strip().lower()[:3]
    if key not in WEEKDAY_INDEX:
        raise OverlayError(f"unknown weekday: {value!r}")
    return WEEKDAY_INDEX[key]


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _matches_nth_weekday(target: date, position: Any, weekday: Any) -> bool:
    wd = _weekday(weekday)
    if target.weekday() != wd:
        return False
    nth = int(position)
    if nth == 0:
        raise OverlayError("nth_weekday position is 1-indexed; 0 has no meaning")
    if nth > 0:
        return (target.day - 1) // 7 == nth - 1
    # Negative: count occurrences of this weekday remaining in the month.
    remaining = 0
    cursor = target
    while cursor.month == target.month:
        remaining += 1
        cursor += timedelta(days=7)
    return remaining == -nth


def _month_days(year: int, month: int) -> int:
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    return (next_first - timedelta(days=1)).day


def _resolve_day(value: int, month_days: int) -> int:
    if value == 0:
        raise OverlayError("day_of_month is 1-indexed; 0 has no meaning")
    if value > 0:
        return value
    return month_days + 1 + value


# --------------------------------------------------------------------------- #
# gtd.md parsing
# --------------------------------------------------------------------------- #

_ADDITION_WITH_RULE_RE = re.compile(r"^(\s*-\s+\[[ xX]\]\s+.*?)\s+`([^`]+)`\s*$")
_ADDITION_PLAIN_RE = re.compile(r"^\s*-\s+\[[ xX]\]\s+(.+?)\s*$")
_REMOVAL_WITH_RULE_RE = re.compile(r"^\s*-\s+(.*?)\s+`([^`]+)`\s*$")
_REMOVAL_PLAIN_RE = re.compile(r"^\s*-\s+(.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)(?:\s+`([^`]+)`)?\s*$")


def parse_overlays(
    gtd_path: Path | None,
    additions_heading: str = "Additions",
    removals_heading: str = "Removals",
) -> tuple[list[Addition], list[Removal]]:
    if not gtd_path or not gtd_path.exists():
        return [], []
    lines = gtd_path.read_text(encoding="utf-8").splitlines()
    additions = _parse_section(lines, additions_heading, kind="addition")
    removals = _parse_section(lines, removals_heading, kind="removal")
    return additions, removals


def list_section_names(
    gtd_path: Path | None,
    additions_heading: str = "Additions",
    removals_heading: str = "Removals",
) -> list[str]:
    """Return unique h3 section names that carry rules, across both overlay h2s."""
    if not gtd_path or not gtd_path.exists():
        return []
    lines = gtd_path.read_text(encoding="utf-8").splitlines()
    seen: list[str] = []
    for heading in (additions_heading, removals_heading):
        start = _find_h2(lines, heading)
        if start is None:
            continue
        end = _next_h2(lines, start + 1)
        for raw in lines[start + 1 : end]:
            h3 = _H3_RE.match(raw)
            if h3 and h3.group(2) is not None:
                name = h3.group(1).strip()
                if name and name not in seen:
                    seen.append(name)
    return seen


def _parse_section(lines: list[str], heading: str, *, kind: str):
    start = _find_h2(lines, heading)
    if start is None:
        return []
    end = _next_h2(lines, start + 1)

    out: list = []
    current_name: str | None = None
    current_rule: Rule | None = None
    in_named_section = False

    for raw in lines[start + 1 : end]:
        h3 = _H3_RE.match(raw)
        if h3:
            current_name = h3.group(1).strip()
            rule_str = h3.group(2)
            current_rule = parse_rule(rule_str) if rule_str else None
            in_named_section = True
            continue

        if in_named_section:
            if current_rule is None:
                continue  # h3 without rule — informational heading, skip its items
            item = _parse_in_section(raw, kind, current_rule, current_name)
        else:
            item = _parse_with_inline_rule(raw, kind)

        if item is not None:
            out.append(item)
    return out


def _parse_with_inline_rule(line: str, kind: str):
    if kind == "addition":
        match = _ADDITION_WITH_RULE_RE.match(line)
        if not match:
            return None
        return Addition(text=match.group(1).rstrip(), rule=parse_rule(match.group(2)))
    match = _REMOVAL_WITH_RULE_RE.match(line)
    if not match:
        return None
    pattern = match.group(1).strip()
    if not pattern:
        return None
    return Removal(pattern=pattern, rule=parse_rule(match.group(2)))


def _parse_in_section(line: str, kind: str, rule: Rule, section: str | None):
    if kind == "addition":
        match = _ADDITION_PLAIN_RE.match(line)
        if not match:
            return None
        return Addition(text=f"- [ ] {match.group(1).strip()}", rule=rule, section=section)
    match = _REMOVAL_PLAIN_RE.match(line)
    if not match:
        return None
    pattern = match.group(1).strip()
    if not pattern:
        return None
    return Removal(pattern=pattern, rule=rule, section=section)


def _find_h2(lines: list[str], heading: str) -> int | None:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$")
    for idx, line in enumerate(lines):
        if pattern.match(line):
            return idx
    return None


def _next_h2(lines: list[str], start: int) -> int:
    for idx in range(start, len(lines)):
        if re.match(r"^##\s+", lines[idx]):
            return idx
    return len(lines)


def active_additions(
    additions: list[Addition],
    target: date,
    override: str | None = None,
    suppress_named: bool = False,
) -> list[Addition]:
    return [a for a in additions if _fires(a, target, override, suppress_named)]


def active_removals(
    removals: list[Removal],
    target: date,
    override: str | None = None,
    suppress_named: bool = False,
) -> list[Removal]:
    return [r for r in removals if _fires(r, target, override, suppress_named)]


def _fires(item, target: date, override: str | None, suppress_named: bool) -> bool:
    if override and item.section == override:
        return True
    if suppress_named and item.section is not None:
        return False
    return item.rule.matches(target)


def apply_removals(lines: list[str], removals: list[Removal]) -> list[str]:
    if not removals:
        return lines
    patterns = [r.pattern for r in removals]
    return [line for line in lines if not any(p in line for p in patterns)]

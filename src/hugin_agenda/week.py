"""Read-only overview of the coming week: calendar, dated additions and routines.

`hugin-agenda --week` answers "what does my week look like?" before it starts.
Each day applies the same overlay rules as the daily agenda, so it shows what
that day's agenda will get. Two things are left out on purpose: the weekday
task lists under `## Week`, which are planning input rather than fixed
commitments, and checkboxes, since nothing here is meant to be ticked.

Dated additions (a bare date) are listed on their day. Unchecked ones whose
dates have all passed are collected under an overdue heading at the top. A
date range is a window rather than a task waiting to be done, so it counts as
a routine, like everything else from the overlays and the base template:
routines that fire every day are summarised on one line, the rest are shown in
a table with one column per day.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from .overlays import Addition, Removal, active_additions, active_removals, apply_removals

WEEK_DAYS = 7
DATED_RULE_KEYS = {"dates"}

LABELS: dict[str, dict[str, Any]] = {
    "en": {
        "week": "Week",
        "overdue": "Overdue",
        "booked": "{hours} h booked",
        "clash": "clash",
        "all_day": "all day",
        "routine": "Routine",
        "every_day": "Every day",
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "decimal": ".",
    },
    "sv": {
        "week": "Vecka",
        "overdue": "Försenat",
        "booked": "{hours} h bokat",
        "clash": "krock",
        "all_day": "heldag",
        "routine": "Rutin",
        "every_day": "Varje dag",
        "weekdays": ["mån", "tis", "ons", "tor", "fre", "lör", "sön"],
        "decimal": ",",
    },
}

_CHECKBOX_RE = re.compile(r"^\s*-\s+\[[ xX]\]\s+")
_TIME_MARKER_RE = re.compile(r"\s*\*\s*~?\{\s*([^}]*?)\s*\}\s*\*")
_WIKILINK_RE = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")


@dataclass
class DayPlan:
    day: date
    events: list[Any]  # agenda.CalendarEvent: title, start, end, all_day
    dated: list[str]
    routines: list[str]


def item_text(line: str) -> str:
    """Turn an agenda line into display text.

    Drops the checkbox, shows wikilinks by their label and moves an agenda
    time marker (`*~{15:00 - 15:30}*`) to the end as `15:00–15:30`.
    """
    text = _CHECKBOX_RE.sub("", line.strip())
    marker = _TIME_MARKER_RE.search(text)
    text = _WIKILINK_RE.sub(r"\1", _TIME_MARKER_RE.sub("", text)).strip()
    if marker:
        text += " " + re.sub(r"\s*-\s*", "–", marker.group(1))
    return text


def template_routines(template_lines: Iterable[str]) -> list[str]:
    return [line for line in template_lines if _CHECKBOX_RE.match(line)]


def is_dated(addition: Addition) -> bool:
    keys = set(addition.rule.raw)
    return addition.section is None and bool(keys) and keys <= DATED_RULE_KEYS


def last_date(addition: Addition) -> date:
    return max(date.fromisoformat(str(d)) for d in addition.rule.raw["dates"])


def overdue_additions(additions: list[Addition], start: date) -> list[tuple[date, str]]:
    """Unchecked dated additions whose dates all lie before `start`, oldest first."""
    out = [
        (last_date(a), item_text(a.text))
        for a in additions
        if is_dated(a) and not a.checked and last_date(a) < start
    ]
    return sorted(out)


def plan_week(
    start: date,
    events_by_day: dict[date, list[Any]],
    template_lines: list[str],
    additions: list[Addition],
    removals: list[Removal],
    override: str | None = None,
    suppress_named: bool = False,
) -> list[DayPlan]:
    base = template_routines(template_lines)
    plans: list[DayPlan] = []
    for offset in range(WEEK_DAYS):
        day = start + timedelta(days=offset)
        fired = [
            a
            for a in active_additions(additions, day, override, suppress_named)
            if not (is_dated(a) and a.checked)
        ]
        rems = active_removals(removals, day, override, suppress_named)
        dated = apply_removals([a.text for a in fired if is_dated(a)], rems)
        routines = apply_removals(base + [a.text for a in fired if not is_dated(a)], rems)
        plans.append(
            DayPlan(
                day=day,
                events=events_by_day.get(day, []),
                dated=[item_text(line) for line in dated],
                routines=list(dict.fromkeys(item_text(line) for line in routines)),
            )
        )
    return plans


def booked_hours(events: list[Any], day: date) -> float:
    """Hours covered by timed events on `day`, overlaps counted once."""
    tz = next((e.start.tzinfo for e in events), None)
    day_start = datetime.combine(day, time(0, 0), tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    spans = sorted(
        (max(e.start, day_start), min(e.end, day_end))
        for e in events
        if not e.all_day and e.end > day_start and e.start < day_end
    )
    total = timedelta()
    cur_start = cur_end = None
    for span_start, span_end in spans:
        if cur_end is not None and span_start <= cur_end:
            cur_end = max(cur_end, span_end)
            continue
        if cur_end is not None:
            total += cur_end - cur_start
        cur_start, cur_end = span_start, span_end
    if cur_end is not None:
        total += cur_end - cur_start
    return total.total_seconds() / 3600


def clashing(events: list[Any]) -> set[int]:
    """Indexes of timed events that overlap another timed event."""
    timed = [(i, e) for i, e in enumerate(events) if not e.all_day]
    return {
        i
        for i, a in timed
        for j, b in timed
        if i != j and a.start < b.end and b.start < a.end
    }


def _date_label(day: date, language: str) -> str:
    if language == "sv":
        return f"{day.day}/{day.month}"
    return day.strftime("%b %d").replace(" 0", " ")


def _hours_label(hours: float, labels: dict[str, Any]) -> str:
    text = f"{hours:.1f}".removesuffix(".0").replace(".", labels["decimal"])
    return labels["booked"].format(hours=text)


def render_week(
    plans: list[DayPlan],
    overdue: list[tuple[date, str]],
    language: str = "en",
) -> str:
    labels = LABELS.get(language, LABELS["en"])
    first, last = plans[0].day, plans[-1].day
    week = first.isocalendar()[1]
    out = [
        f"# {labels['week']} {week} · "
        f"{_date_label(first, language)}–{_date_label(last, language)}",
        "",
    ]

    if overdue:
        out.append(f"**{labels['overdue']}**")
        out += [f"- {text} ({_date_label(day, language)})" for day, text in overdue]
        out.append("")

    for plan in plans:
        events = sorted(plan.events, key=lambda e: (not e.all_day, e.start))
        hours = booked_hours(events, plan.day)
        heading = f"**{labels['weekdays'][plan.day.weekday()]} {_date_label(plan.day, language)}**"
        if hours:
            heading += f" · {_hours_label(hours, labels)}"
        out.append(heading)
        clash = clashing(events)
        for i, event in enumerate(events):
            if event.all_day:
                out.append(f"- {labels['all_day']}: {event.title}")
                continue
            line = f"- {event.start:%H:%M}–{event.end:%H:%M} {event.title}"
            if i in clash:
                line += f" ⚠️ {labels['clash']}"
            out.append(line)
        out += [f"- 📌 {text}" for text in plan.dated]
        if not events and not plan.dated:
            out.append("- –")
        out.append("")

    every_day = set.intersection(*(set(p.routines) for p in plans))
    some_days = list(dict.fromkeys(r for p in plans for r in p.routines if r not in every_day))
    if some_days:
        days = [labels["weekdays"][p.day.weekday()] for p in plans]
        out.append(f"| {labels['routine']} | " + " | ".join(days) + " |")
        out.append("|---|" + "---|" * len(plans))
        for routine in some_days:
            marks = ["●" if routine in p.routines else "" for p in plans]
            out.append(f"| {routine} | " + " | ".join(marks) + " |")
        out.append("")
    if every_day:
        ordered = [r for r in plans[0].routines if r in every_day]
        out.append(f"*{labels['every_day']}:* " + ", ".join(ordered))
        out.append("")
    return "\n".join(out)

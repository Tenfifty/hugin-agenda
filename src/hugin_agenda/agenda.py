"""Generate a daily agenda from calendar + GTD."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .config import AgendaConfig, load_config
from .overlays import (
    OverlayWarning,
    Removal,
    active_additions,
    active_removals,
    apply_removals,
    list_section_names,
    parse_overlays_with_warnings,
)


@dataclass
class CalendarEvent:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False


@dataclass
class AgendaItem:
    at: datetime
    lines: list[str]
    kind: str


@dataclass
class GtdTaskBlock:
    lines: list[str]
    duration_slots: int


@dataclass
class FixedAgendaBlock:
    lines: list[str]
    start: datetime
    end: datetime


class AgendaError(RuntimeError):
    pass


def parse_args(cfg: AgendaConfig) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate agenda template for today/tomorrow with calendar events and "
            "weekday GTD tasks."
        )
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Generate agenda for today (default: tomorrow)",
    )
    parser.add_argument(
        "--date",
        help="Generate agenda for a specific date (YYYY-MM-DD). Overrides --today.",
    )
    parser.add_argument(
        "--template",
        help=f"Override base template (default: {cfg.base_template!r}).",
    )
    parser.add_argument(
        "--calendar",
        default=cfg.calendar_id,
        help=f"Calendar id to read (default: {cfg.calendar_id})",
    )
    parser.add_argument(
        "--override",
        help=(
            "Force a named gtd.md overlay section (its items fire regardless of "
            "the section's date rule). Other sections still evaluate normally."
        ),
    )
    parser.add_argument(
        "--no-named-sections",
        action="store_true",
        help=(
            "Suppress every named overlay section regardless of date rules; "
            "only the base template plus per-line additions/removals fire."
        ),
    )
    parser.add_argument(
        "--list-overrides",
        action="store_true",
        help="Print the names of overlay sections in gtd.md and exit.",
    )
    args = parser.parse_args()
    if args.override and args.no_named_sections:
        parser.error("--override and --no-named-sections are mutually exclusive")
    return args


def local_tzinfo():
    return datetime.now().astimezone().tzinfo


def template_path(template_name: str, cfg: AgendaConfig) -> Path:
    return cfg.templates_dir / f"agenda_{template_name}.md"


def gws_environment(cfg: AgendaConfig) -> dict[str, str]:
    env = os.environ.copy()
    if cfg.gws_config_dir:
        env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = str(cfg.gws_config_dir)
        env["GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"] = str(
            cfg.gws_config_dir / "credentials.json"
        )
    return env


def resolve_gws_bin(cfg: AgendaConfig) -> str:
    preferred = os.environ.get("HUGIN_GWS_BIN") or cfg.gws_bin
    preferred_path = Path(preferred).expanduser()
    if preferred_path.is_absolute() and preferred_path.exists() and os.access(preferred_path, os.X_OK):
        return str(preferred_path)
    if shutil.which(preferred):
        return preferred
    raise FileNotFoundError(
        f"gws binary {preferred!r} not found on PATH. "
        "Install the Google Workspace CLI or set gws_bin / HUGIN_GWS_BIN."
    )


def run_gws(cfg: AgendaConfig, *args: str) -> dict[str, Any]:
    gws_bin = resolve_gws_bin(cfg)
    result = subprocess.run(
        [gws_bin, *args],
        capture_output=True,
        text=True,
        env=gws_environment(cfg),
    )

    payload: dict[str, Any] | None = None
    stdout = result.stdout.strip()
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = None

    if result.returncode != 0:
        message = result.stderr.strip()
        if payload and "error" in payload:
            message = str(payload["error"].get("message", message))
        raise AgendaError(message or f"{gws_bin} {' '.join(args)} failed")

    if not payload:
        raise AgendaError(f"Unexpected gws output for command: {' '.join(args)}")
    if "error" in payload:
        raise AgendaError(str(payload["error"].get("message", "gws returned an error")))
    return payload


def parse_event_datetime(raw: dict[str, Any]) -> tuple[datetime | None, bool]:
    if "dateTime" in raw:
        value = raw["dateTime"].replace("Z", "+00:00")
        return datetime.fromisoformat(value).astimezone(local_tzinfo()), False
    if "date" in raw:
        value = datetime.fromisoformat(raw["date"]).replace(tzinfo=local_tzinfo())
        return value, True
    return None, False


def fetch_events(cfg: AgendaConfig, target_date: date, calendar_id: str) -> list[CalendarEvent]:
    tz = local_tzinfo()
    day_start = datetime.combine(target_date, time(0, 0), tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    payload = run_gws(
        cfg,
        "calendar",
        "events",
        "list",
        "--params",
        json.dumps(
            {
                "calendarId": calendar_id,
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "singleEvents": True,
                "orderBy": "startTime",
                "showDeleted": False,
                "maxResults": 250,
            }
        ),
    )
    events: list[CalendarEvent] = []
    for item in payload.get("items", []):
        if item.get("status") == "cancelled":
            continue

        start, start_all_day = parse_event_datetime(item.get("start", {}))
        end, end_all_day = parse_event_datetime(item.get("end", {}))
        if not start or not end:
            continue

        all_day = start_all_day or end_all_day
        if all_day:
            end = end - timedelta(minutes=1)
        if end <= start:
            end = start + timedelta(minutes=30)

        title = str(item.get("summary") or "(untitled)")
        events.append(CalendarEvent(title=title, start=start, end=end, all_day=all_day))
    return events


def event_line(event: CalendarEvent) -> str:
    start_text = event.start.strftime("%H:%M")
    end_text = event.end.strftime("%H:%M")
    return f"- [ ] {event.title} *{{{start_text} - {end_text}}}*"


_TIME_MARKER_RE = re.compile(
    r"\*\s*~?\{\s*([01]?\d|2[0-3]):([0-5]\d)"
    r"(?:\s*-\s*([01]?\d|2[0-3]):([0-5]\d))?\s*\}\s*\*"
)


def timed_block_from_task(
    task: GtdTaskBlock,
    target_date: date,
    slot_minutes: int,
) -> FixedAgendaBlock | None:
    if not task.lines:
        return None
    match = _TIME_MARKER_RE.search(task.lines[0])
    if not match:
        return None

    tz = local_tzinfo()
    start = datetime.combine(
        target_date,
        time(int(match.group(1)), int(match.group(2))),
        tzinfo=tz,
    )
    duration = timedelta(minutes=slot_minutes * max(1, task.duration_slots))
    if match.group(3) is not None and match.group(4) is not None:
        end = datetime.combine(
            target_date,
            time(int(match.group(3)), int(match.group(4))),
            tzinfo=tz,
        )
        if end <= start:
            end = start + duration
    else:
        end = start + duration
    return FixedAgendaBlock(lines=task.lines, start=start, end=end)


def split_fixed_task_blocks(
    tasks: list[GtdTaskBlock],
    target_date: date,
    slot_minutes: int,
) -> tuple[list[FixedAgendaBlock], list[GtdTaskBlock]]:
    fixed: list[FixedAgendaBlock] = []
    floating: list[GtdTaskBlock] = []
    for task in tasks:
        fixed_block = timed_block_from_task(task, target_date, slot_minutes)
        if fixed_block is None:
            floating.append(task)
        else:
            fixed.append(fixed_block)
    return fixed, floating


def replace_header_date(template_lines: list[str], target_date: date) -> None:
    for idx, line in enumerate(template_lines):
        if line.startswith("## "):
            header = f"## <{target_date.isoformat()} {target_date.strftime('%a')}>"
            template_lines[idx] = header
            return


def find_agenda_insertion_index(lines: list[str]) -> int:
    """Return index of the marker blank line in the template.

    The marker is the first blank line whose preceding non-blank line is a
    list item (``- ...``). Items are inserted at this index; the renderer
    consumes the blank line so it acts as a marker only. Templates without a
    marker fall back to appending at the end.
    """
    for idx, line in enumerate(lines):
        if line.strip():
            continue
        for back in range(idx - 1, -1, -1):
            prev = lines[back]
            if not prev.strip():
                continue
            if prev.lstrip().startswith("-"):
                return idx
            break
    return len(lines)


def insert_overlay_warnings(
    lines: list[str],
    warnings: list[OverlayWarning],
) -> list[str]:
    if not warnings:
        return lines

    block = ["> [!warning] hugin-agenda overlay warnings"]
    for warning in warnings:
        block.append(
            f"> - gtd.md:{warning.line_number} "
            f"(## {warning.heading}): {warning.message}"
        )
        block.append(f">   Source: {warning.line}")
    block.append("")

    insert_idx = 0
    for idx, line in enumerate(lines):
        if line.startswith("### Agenda"):
            insert_idx = idx
            break
        if idx == 0 and line.startswith("## "):
            insert_idx = 1
    return lines[:insert_idx] + block + lines[insert_idx:]


def parse_gtd_week_tasks(cfg: AgendaConfig, target_date: date) -> list[GtdTaskBlock]:
    if not cfg.gtd_path or not cfg.gtd_path.exists():
        return []
    text = cfg.gtd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    week_headings = ("Vecka", "Week")
    week_start = None
    for idx, line in enumerate(lines):
        for heading in week_headings:
            if re.match(rf"^##\s+{re.escape(heading)}\s*$", line):
                week_start = idx + 1
                break
        if week_start is not None:
            break
    if week_start is None:
        return []

    week_end = len(lines)
    for idx in range(week_start, len(lines)):
        if re.match(r"^##\s+", lines[idx]):
            week_end = idx
            break

    weekday_names = cfg.resolved_weekday_names()
    weekday_name = weekday_names[target_date.weekday()]
    day_start = None
    for idx in range(week_start, week_end):
        if re.match(rf"^###\s+{re.escape(weekday_name)}\s*$", lines[idx]):
            day_start = idx + 1
            break
    if day_start is None:
        return []

    day_end = week_end
    for idx in range(day_start, week_end):
        if re.match(r"^###\s+", lines[idx]):
            day_end = idx
            break

    day_lines = lines[day_start:day_end]
    top_level_task_re = re.compile(r"^-\s+\[\s\]\s+.*\S\s*$")
    indented_line_re = re.compile(r"^[ \t]+")
    indented_checkbox_re = re.compile(r"^[ \t]+-\s+\[[ xX]\]\s+")

    tasks: list[GtdTaskBlock] = []
    idx = 0
    while idx < len(day_lines):
        line = day_lines[idx]
        if not top_level_task_re.match(line):
            idx += 1
            continue

        block_lines = [line]
        subitem_count = 0
        cursor = idx + 1
        while cursor < len(day_lines):
            candidate = day_lines[cursor]
            if not indented_line_re.match(candidate):
                break
            block_lines.append(candidate)
            if indented_checkbox_re.match(candidate):
                subitem_count += 1
            cursor += 1

        duration_slots = max(1, subitem_count)
        tasks.append(GtdTaskBlock(lines=block_lines, duration_slots=duration_slots))
        idx = cursor

    return tasks


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def ceil_to_slot(dt_value: datetime, slot_minutes: int) -> datetime:
    minute_block = (dt_value.minute // slot_minutes) * slot_minutes
    floored = dt_value.replace(minute=minute_block, second=0, microsecond=0)
    if floored == dt_value.replace(second=0, microsecond=0):
        return floored
    return floored + timedelta(minutes=slot_minutes)


def first_overlap(
    intervals: list[tuple[datetime, datetime]],
    start: datetime,
    end: datetime,
) -> tuple[datetime, datetime] | None:
    for busy_start, busy_end in intervals:
        if busy_end <= start:
            continue
        if busy_start >= end:
            return None
        if busy_start < end and busy_end > start:
            return (busy_start, busy_end)
    return None


def schedule_tasks(
    cfg: AgendaConfig,
    target_date: date,
    events: list[CalendarEvent],
    tasks: list[GtdTaskBlock],
    busy_blocks: list[tuple[datetime, datetime]] | None = None,
) -> list[tuple[GtdTaskBlock, datetime]]:
    if not tasks:
        return []

    tz = local_tzinfo()
    busy = merge_intervals(
        [(event.start, event.end) for event in events] + (busy_blocks or [])
    )
    cursor = datetime.combine(target_date, time(cfg.day_start_hour, 0), tzinfo=tz)
    assignments: list[tuple[GtdTaskBlock, datetime]] = []
    slot = timedelta(minutes=cfg.task_slot_minutes)

    for task in tasks:
        attempts = 0
        task_duration = slot * max(1, task.duration_slots)
        while attempts < 2000:
            attempts += 1
            slot_end = cursor + task_duration
            overlap = first_overlap(busy, cursor, slot_end)
            if overlap is None:
                assignments.append((task, cursor))
                cursor = slot_end
                break
            cursor = ceil_to_slot(overlap[1], cfg.task_slot_minutes)
        else:
            assignments.append((task, cursor))
            cursor += task_duration
    return assignments


def build_agenda_items(
    events: list[CalendarEvent],
    fixed_blocks: list[FixedAgendaBlock],
    scheduled_tasks: list[tuple[GtdTaskBlock, datetime]],
) -> list[AgendaItem]:
    items: list[AgendaItem] = []
    for event in events:
        items.append(AgendaItem(at=event.start, lines=[event_line(event)], kind="event"))
    for fixed_block in fixed_blocks:
        items.append(
            AgendaItem(at=fixed_block.start, lines=fixed_block.lines, kind="fixed")
        )
    for task_block, when in scheduled_tasks:
        items.append(AgendaItem(at=when, lines=task_block.lines, kind="task"))

    kind_order = {"event": 0, "fixed": 0, "task": 1}
    items.sort(key=lambda item: (item.at, kind_order.get(item.kind, 99)))
    return items


def render_agenda(
    cfg: AgendaConfig,
    target_date: date,
    template_name: str,
    events: list[CalendarEvent],
    tasks: list[GtdTaskBlock],
    removals: list[Removal] | None = None,
    overlay_warnings: list[OverlayWarning] | None = None,
) -> str:
    path = template_path(template_name, cfg)
    if not path.exists():
        raise AgendaError(f"Template not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    replace_header_date(lines, target_date)

    insertion_idx = find_agenda_insertion_index(lines)
    fixed_blocks, floating_tasks = split_fixed_task_blocks(
        tasks,
        target_date,
        cfg.task_slot_minutes,
    )
    busy_blocks = [(block.start, block.end) for block in fixed_blocks]
    scheduled_tasks = schedule_tasks(
        cfg,
        target_date,
        events,
        floating_tasks,
        busy_blocks,
    )
    items = build_agenda_items(events, fixed_blocks, scheduled_tasks)
    tail_idx = insertion_idx
    if insertion_idx < len(lines) and not lines[insertion_idx].strip():
        tail_idx += 1

    output_lines = lines[:insertion_idx]
    if items:
        for item in items:
            output_lines.extend(item.lines)
    output_lines.extend(lines[tail_idx:])
    output_lines = apply_removals(output_lines, removals or [])
    output_lines = insert_overlay_warnings(output_lines, overlay_warnings or [])
    return "\n".join(output_lines) + "\n\n"


def main() -> int:
    cfg = load_config()
    args = parse_args(cfg)
    additions_heading, removals_heading = cfg.resolved_overlay_headings()
    if args.list_overrides:
        for name in list_section_names(cfg.gtd_path, additions_heading, removals_heading):
            sys.stdout.write(name + "\n")
        return 0
    today = date.today()
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError as exc:
            print(f"Error: invalid --date {args.date!r}: {exc}", file=sys.stderr)
            return 1
    else:
        target_date = today if args.today else today + timedelta(days=1)
    template_name = args.template or cfg.base_template

    try:
        events = fetch_events(cfg, target_date, args.calendar)
        tasks = parse_gtd_week_tasks(cfg, target_date)
        additions, removals, overlay_warnings = parse_overlays_with_warnings(
            cfg.gtd_path, additions_heading, removals_heading
        )
        for addition in active_additions(
            additions, target_date, args.override, args.no_named_sections
        ):
            tasks.append(GtdTaskBlock(lines=[addition.text], duration_slots=1))
        active_rems = active_removals(
            removals, target_date, args.override, args.no_named_sections
        )
        agenda = render_agenda(
            cfg=cfg,
            target_date=target_date,
            template_name=template_name,
            events=events,
            tasks=tasks,
            removals=active_rems,
            overlay_warnings=overlay_warnings,
        )
    except (AgendaError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(agenda)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

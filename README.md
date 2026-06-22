# hugin-agenda

Generate a daily agenda Markdown file from your Google Calendar and a GTD
file. Part of the [Hugin](https://github.com/Tenfifty/hugin) personal productivity stack.

Given a date, hugin-agenda:

1. Loads a single base template (or `--template <name>`).
2. Fetches calendar events via the Google Workspace CLI (`gws`).
3. Parses the current week's GTD tasks for that weekday, plus date-rule
   overlays from `## Additions` / `## Removals` in the same GTD file.
4. Schedules GTD tasks + untimed active additions around calendar events and
   timed additions in 30-minute slots.
5. Strips lines matched by active removals.
6. Prints the resulting Markdown to stdout — ready to paste into your vault.

There are also some utility functions to integrate this with Obsidian, for example syncing checked agenda items from `journal.md` to `gtd.md`.

## Workflow

The tool is built around two loops. Concrete commands and Obsidian wiring
live in later sections; this is the mental model.

**Daily** (in the morning or, better, the day before):

1. Open your daily journal note in Obsidian.
2. Run the `agenda_choice` QuickAdd macro (or `hugin-agenda --today` / `hugin-agenda --tomorrow`) to
   insert the generated agenda at the cursor.
3. Work the day. Tick checkboxes in the journal as you go;
   `Ctrl+Shift+Enter` (bound to `scripts/toggle_todo_sync_gtd.js`) toggles
   the box and syncs the state back into `gtd.md`, so tasks completed in
   the journal disappear from next week's planning surface.
4. Anything left unchecked at end of day stays in `gtd.md`, ready for
   tomorrow's agenda or weekly review.

**Continuously**
1. During the day, add new tasks and ideas to the capture sections in `gtd.md`. See below.
2. Add date-specific tasks (for example reminders or other things not fitting a calendar booking) or recurring tasks to
   `## Additions` with a rule (see [Overlays](#overlays-per-day-additions-and-removals)).

**Weekly** (Sunday or Monday):

1. Open `gtd.md`.
2. Clear out last week's `### Monday`…`### Sunday` blocks under `## Week`.
   Checked items are done; unchecked items get pulled forward to a day
   this week, dropped, or moved into a backlog section.
3. Walk the backlog sections (see below) and promote anything ripe into
   the right weekday under `## Week`.
4. Optionally run `hugin-agenda-rotate-journal` to archive last week's journal and
   reset `journal.md` for the new week.

### Suggested gtd.md layout

Only `## Week` (and weekdays), `## Additions`, and `## Removals` are special to
hugin-agenda. Everything else is free-form — useful as a staging area for
weekly planning. A layout that works well:

```markdown
# GTD

## Week
### Monday
- [ ] Standup notes
### Tuesday
...
## Soon
- [ ] Reach out to N about contract
- [ ] Fix kitchen faucet

## Later
### Work
- [ ] Investigate replacing X
- [ ] Read paper on Y

### Personal
...

## Purchases
- [ ] New running shoes
- [ ] Replacement HDMI cable

## Waiting for
- [ ] Invoice from supplier (sent 2026-05-20)

## Someday / Maybe
- [ ] Sabbatical planning

## Additions
- [ ] Follow up on quote `2026-06-17`
- [ ] Take out trash `{every_n_days_from: [2026-01-07, 14]}`

## Removals
...
```

Pick whatever extra sections fit your life — common ones are **Soon**
(this week or next), **Later** (this quarter), **Purchases**, **Waiting
for** (delegated items, often with a date sent), and **Someday / Maybe**
(David Allen style: things you've considered but aren't committing to).
During weekly planning you skim each section and move items into the
days under `## Week`.

## Install

```bash
pip install -e ../hugin -e . --break-system-packages
```

Requires Python 3.10+, the shared `hugin` package, and the `gws` CLI on PATH
(or top-level `gws_bin` set in config).

## Configure

Run `hugin-init` (shipped with the shared `hugin` package) to scaffold
`~/.config/hugin/hugin.yaml` and a vault layout. Then copy
`config.example.yaml` into `~/.config/hugin/agenda.yaml` for the
agenda-specific bits.

- `hugin.yaml` — shared across all hugin-* tools (language, vault, gws, journal)
- `agenda.yaml` — agenda-specific (templates, GTD path, calendar id)

The tool-specific file overrides the shared file; values are deep-merged.
Override the config dir with `HUGIN_CONFIG_DIR=/path`.

## Use

```bash
hugin-agenda                       # agenda for tomorrow
hugin-agenda --today               # agenda for today
hugin-agenda --date 2026-05-01
hugin-agenda --template kontor     # use agenda_kontor.md instead of agenda_base.md
```

### Rotate the journal

```bash
hugin-agenda-rotate-journal --dry-run
hugin-agenda-rotate-journal
hugin-agenda-rotate-journal --open-archive
hugin-agenda-rotate-journal --force
```

Reads `journal_path` from shared config. Archives the current `journal.md` to
`<archive_dirname>/journal_yymmdd-yymmdd.md` (defaults to `archive/` for
`language: en`, `arkiv/` for `sv`), using the inclusive range from the earliest
to latest dated entry, then resets `journal.md` to `# Journal YYYY`.
Pass `--open-archive` to open the new archive in Obsidian.

For Obsidian, `--open-archive` is useful from a Templater or shell-command
shortcut. A Templater template can run the command without inserting output:

```md
<%* await tp.user.RotateJournal() %>
```

Configure `RotateJournal` as a Templater system command, for example:

```bash
hugin-agenda-rotate-journal --open-archive
```

### Sync checked journal todos back to GTD

```bash
hugin-agenda-sync-gtd-checkbox --line "- [x] Follow up on agenda draft"
```

The command reads `agenda.gtd_path`, finds the single matching checkbox line
outside the date-rule overlay sections (`## Additions` / `## Removals`, or
Swedish equivalents), and updates only its checkbox marker. Matching ignores
leading whitespace and the previous checkbox state, so journal subitems can
sync back to indented GTD subitems.

For Obsidian, `scripts/toggle_todo_sync_gtd.js` can be used as a QuickAdd user
script. Bind that QuickAdd choice to `Ctrl+Shift+Enter` in place of
Obsidian's built-in checklist toggle; it runs the normal toggle first, then
syncs when the active file is `journal/journal.md`.
If Obsidian was launched from a desktop environment and cannot find the command,
set `HUGIN_AGENDA_SYNC_GTD_CHECKBOX` to the full script path, or change the
`SYNC` constant in your vault copy.

## GTD-line research agent

`hugin-agenda-research` turns a single GTD line into prepared groundwork. Put
the cursor on a task line in Obsidian, hit a hotkey, and a background agent
(codex by default) researches it — reading vault files (meeting notes, project
docs) and the web — then writes its findings to a sidecar note linked from the
line. The point is to lower the activation energy of the task: when you come
back to do it, the prep is already there.

### Workflow

The hotkey is state-aware, driven by a marker it appends to the line:

| Marker   | Meaning     | Hotkey again does                                  |
| -------- | ----------- | -------------------------------------------------- |
| (none)   | not started | create sidecar, stamp link + 🔄, launch the agent  |
| 🔄       | running     | nothing (already running)                          |
| ❓       | needs input | resume — you answered its questions in the sidecar |
| ✅       | done        | nothing (open the sidecar)                         |
| 🛑       | failed      | retry                                              |

The sidecar's frontmatter `status:` is the source of truth; the marker is only
a cache, so a marker that didn't update (e.g. a write clobbered by Obsidian's
open buffer) self-heals on the next hotkey press. Sidecars live in
`<research_dir>/YYYY-MM/<slug>.md` (default `gtd-research/` next to gtd.md) with
a `## Research` and a `## Logg` section; a questions section appears only when
the agent needs an answer from you.

### Inline instructions

Anything after a `` // `` on the task line is passed to the agent as a direct
instruction (and kept out of the slug). URLs (`https://…`) are not mistaken for
the separator.

```markdown
- [ ] Rent a car for a month this summer // focus on long-term rental, cheapest
```

### Configure

Provider and binary come from the shared `llm:` section in `hugin.yaml`
(default provider `codex`). Agenda-specific keys in `agenda.yaml`:

- `research_dir` — sidecar folder (default `gtd-research/` next to gtd.md)
- `research_effort` — codex `model_reasoning_effort`: `none | minimal | low |
  medium | high | xhigh` (default `high`)
- `research_network` — allow web access (default `true`)
- `research_prompt_template` — override the packaged prompt

Requires the `codex` CLI on PATH (and `node`, which its shebang needs). The
agent runs `codex exec` in the vault root with `-s workspace-write`, so it can
read vault files and edit the sidecar.

### Obsidian integration

`scripts/research_line.js` is a QuickAdd user script.

1. Copy it into your QuickAdd scripts folder.
2. Create a QuickAdd **Macro** choice that runs the script (the type selector is
   the button next to the name field — switch it from "Template" to "Macro").
3. Register the macro as a command (the ⚡ icon) and bind a hotkey under
   Settings → Hotkeys.

`hugin-agenda-research` must be on the PATH of the process that launched
Obsidian. If Obsidian was started from a desktop launcher and can't find it,
set `HUGIN_AGENDA_RESEARCH` to the absolute path at the top of the script.

## Templates

A single base template ships at `src/hugin_agenda/templates/agenda_base.md`.
Point `agenda.templates_dir` at your own directory to use custom ones, and
set `agenda.base_template: <name>` to pick which file is the base (resolves
to `agenda_<name>.md`). `--template <name>` overrides for a single run.

Per-day variation is **not** done with multiple template files — use the
`## Additions` / `## Removals` sections in your GTD file instead (see below).

Each template should have an `## <date>` header (auto-rewritten). To choose
where scheduled items are inserted, put a blank marker line after a list item;
the marker line is consumed in the rendered agenda. Templates without a marker
append scheduled items at the end.

## GTD format

```markdown
## Week            (or "Vecka" in Swedish)
### Monday         (localised by `language` — en/sv built in)
- [ ] Some task
    - [ ] subitem  (each subitem adds a 30m slot to the task's duration)
```

## Overlays: per-day additions and removals

Two optional sections in the same GTD file let you add or strip lines on
specific dates without creating extra template files. Headings follow
`language` (en: `## Additions` / `## Removals`; sv: `## Tillägg` /
`## Borttagningar`; override with `additions_heading` / `removals_heading`).
Lines before any `###` subheading carry per-line rules in backticks; items
under a `### Name `{rule}`` heading inherit the section's rule.

```markdown
## Additions
- [ ] Follow up on thing with Mark `2026-06-17`
- [ ] Take out trash `{every_n_days_from: [2026-01-07, 14]}`

### Weekend `{weekdays: [sat, sun]}`
- [ ] Sauna
- [ ] Cleaning

## Removals
### Office `{weekdays: [mon, thu]}`
- [ ] Exercise
```

**Additions** are appended to the day's task list and scheduled alongside the
weekly tasks. If an addition contains an agenda time marker like
`*{15:00 - 15:30}*` or `*~{15:00}*`, it is treated as a fixed-time item:
it sorts with calendar events and blocks that time for floating tasks. The `~`
marker is preserved for other Hugin tools, such as hugin-meeting.
**Removals** strip any agenda line containing the given substring
(case-sensitive), including calendar event lines — intentional, so vacation
removals also hide work meetings.

### Named sections and manual override

A `### Name `{rule}`` heading attaches the rule to every item below it
(until the next `###`). The name is exposed via:

```bash
hugin-agenda --list-overrides       # prints section names from gtd.md
hugin-agenda --override Office      # forces that section's items today
```

`--override` is additive: the named section fires regardless of its date
rule; other sections still evaluate normally.

## Obsidian integration

A ready-made [QuickAdd](https://github.com/chhoumann/quickadd) macro lives at
`scripts/agenda_choice.js`. It asks Today/Tomorrow, then offers
`(auto)` + every named section from your gtd.md (read live via
`--list-overrides`), then inserts the rendered agenda at the cursor.

Setup:

1. Copy `scripts/agenda_choice.js` into the scripts folder configured in
   QuickAdd settings.
2. Create a QuickAdd macro that runs the script.
3. Bind the macro to a hotkey or expose it through the QuickAdd command palette.

`hugin-agenda` must be on the PATH of the process that launched Obsidian.
If Obsidian was started from a desktop launcher and can't find it, hardcode
the absolute path at the top of the script (`const HUGIN = "..."`).

### Rule syntax

Shorthand forms first, then YAML flow for everything else:

| Rule                                | Meaning                                    |
| ----------------------------------- | ------------------------------------------ |
| `2026-06-17`                        | one exact date                             |
| `2026-07-01..2026-07-21`            | inclusive date range                       |
| `{key: value, ...}`                 | YAML mapping; full grammar below           |

### Matcher keys (all AND together within a rule; lists within a key OR)

| Key                  | Example                                              | Meaning                                                  |
| -------------------- | ---------------------------------------------------- | -------------------------------------------------------- |
| `weekdays`           | `[mon, thu]`                                         | matches if `target.weekday` is in the list               |
| `months`             | `[6, 7, 8]`                                          | matches in June/July/August                              |
| `day_of_month`       | `[1, 15, -1]`                                        | 1st, 15th, or last day; negatives count from end         |
| `nth_weekday`        | `[1, mon]`, `[-1, fri]`                              | 1st Monday / last Friday of the month; 1-indexed         |
| `dates`              | `[2026-06-17, 2026-12-24]`                           | exact dates (any of)                                     |
| `date_ranges`        | `[[2026-07-01, 2026-07-21]]`                         | inclusive ranges (any of)                                |
| `every_n_days_from`  | `[2026-01-07, 28]`                                   | anchor date + cadence; matches anchor, anchor+N, ...     |
| `not`                | `{dates: [2026-12-24]}`                              | nested rule; negated                                     |

`day_of_month` and `nth_weekday` accept negative integers (`-1` = last,
`-2` = second-to-last). Position `0` raises an error.

### Examples

```markdown
- [ ] Every other Wednesday from June 17 `{weekdays: [wed], every_n_days_from: [2026-06-17, 14]}`
- [ ] Last Friday of the month payday `{nth_weekday: [-1, fri]}`
- [ ] Summer Wednesdays only `{weekdays: [wed], months: [6, 7, 8]}`
- [ ] Every Wednesday except Christmas `{weekdays: [wed], not: {dates: [2026-12-24]}}`
```

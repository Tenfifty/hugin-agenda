# hugin-agenda

Generate a daily agenda Markdown file from your Google Calendar and a GTD
file. Part of the [Hugin](https://github.com/Tenfifty/hugin) personal productivity stack.

Given a date, hugin-agenda:

1. Loads a single base template (or `--template <name>`).
2. Fetches calendar events via the Google Workspace CLI (`gws`).
3. Parses the current week's GTD tasks for that weekday, plus date-rule
   overlays from `## Additions` / `## Removals` in the same GTD file.
4. Schedules the GTD tasks + active additions around events in 30-minute slots.
5. Strips lines matched by active removals.
6. Prints the resulting Markdown to stdout — ready to paste into your vault.

## Install

```bash
pip install -e . --break-system-packages
```

Requires Python 3.10+ and the `gws` CLI on PATH (or `gws_bin` set in config).

## Configure

Run `hugin-init` (shipped with the `hugin` shared library) to scaffold
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
hugin-agenda-sync-gtd-checkbox --line "- [x] Spegla GTD-checks"
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

## Templates

A single base template ships at `src/hugin_agenda/templates/agenda_base.md`.
Point `agenda.templates_dir` at your own directory to use custom ones, and
set `agenda.base_template: <name>` to pick which file is the base (resolves
to `agenda_<name>.md`). `--template <name>` overrides for a single run.

Per-day variation is **not** done with multiple template files — use the
`## Additions` / `## Removals` sections in your GTD file instead (see below).

Each template should have an `## <date>` header (auto-rewritten) and may end
with a `- [ ] Agenda 2` sentinel line above which scheduled items are inserted.

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
- [ ] Dentist 14:00 `2026-06-17`
- [ ] Take out glass `{every_n_days_from: [2026-01-07, 28]}`

### Office `{weekdays: [mon, thu]}`
- [ ] Shorter cleanup, 20m
- [ ] Quick lunch

## Removals
### Office `{weekdays: [mon, thu]}`
- Sauna
- Long cleanup, 30m
```

**Additions** are appended to the day's task list and scheduled alongside the
weekly tasks. **Removals** strip any agenda line containing the given
substring (case-sensitive), including calendar event lines — intentional, so
vacation removals also hide work meetings.

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

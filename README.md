# hugin-agenda

Generate a daily agenda Markdown file from your Google Calendar and a GTD
file. Part of the [Hugin](https://github.com/) personal productivity stack.

Given a date, hugin-agenda:

1. Picks an agenda template based on the weekday (or `--template <name>`).
2. Fetches calendar events via the [Google Workspace CLI](https://github.com/)
   (`gws`).
3. Parses the current week's GTD tasks for that weekday.
4. Schedules the GTD tasks around the events in 30-minute slots.
5. Prints the resulting Markdown to stdout — ready to paste into your vault.

## Install

```bash
pip install -e . --break-system-packages
```

Requires Python 3.10+ and the `gws` CLI on PATH (or `gws_bin` set in config).

## Configure

Two YAML files at `~/.config/hugin/` (override the directory with
`HUGIN_CONFIG_DIR`):

- `hugin.yaml` — shared across all hugin-* tools (language, vault, gws, journal).
- `agenda.yaml` — agenda-specific (templates, GTD path, calendar id).

See [`config.example.yaml`](config.example.yaml). The tool-specific file
overrides the shared file; values are deep-merged.

## Use

```bash
hugin-agenda                       # agenda for tomorrow
hugin-agenda --today               # agenda for today
hugin-agenda --date 2026-05-01
hugin-agenda --template weekend    # force a specific template
```

### Rotate the journal at year boundaries

```bash
hugin-agenda-rotate-journal --dry-run
hugin-agenda-rotate-journal            # archives last year's entries
hugin-agenda-rotate-journal --year 2024 --force
```

Reads `journal_path` from shared config. Archives to `journal_<year>.md` in
the same directory.

## Templates

Default English templates ship in
`src/hugin_agenda/templates/agenda_{weekday,weekend}.md`. Point
`agenda.templates_dir` at your own directory to use custom ones — the file
name must be `agenda_<template>.md`.

Each template should have an `## <date>` header (auto-rewritten) and may end
with a `- [ ] Agenda 2` sentinel line above which scheduled items are inserted.

## GTD format

The parser looks for:

```markdown
## Week            (or "Vecka" in Swedish)
### Monday         (localised by `language` — en/sv built in)
- [ ] Some task
    - [ ] subitem  (each subitem adds a 30m slot to the task's duration)
```

# hugin-agenda

Generate a daily agenda Markdown file from your Google Calendar and a GTD
file. Part of the [Hugin](https://github.com/Tenfifty/hugin) personal productivity stack.

Given a date, hugin-agenda:

1. Picks an agenda template based on the weekday (or `--template <name>`).
2. Fetches calendar events via the Google Workspace CLI (`gws`).
3. Parses the current week's GTD tasks for that weekday.
4. Schedules the GTD tasks around the events in 30-minute slots.
5. Prints the resulting Markdown to stdout — ready to paste into your vault.

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
hugin-agenda --template weekend    # force a specific template
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

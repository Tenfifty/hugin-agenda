# Repo guidance for Claude / Codex

`hugin-agenda` generates daily agendas from a Google Calendar (via
`gws`) and a weekly GTD markdown file. Part of the [Hugin](../hugin)
personal productivity stack.

The shared contract (config layout, language handling, vault structure,
markdown headers, archive-dir naming) lives in
[`../hugin/CONVENTIONS.md`](../hugin/CONVENTIONS.md). Read that before
touching anything that crosses tool boundaries.

## What's here

- `src/hugin_agenda/config.py` — `AgendaConfig` subclasses `hugin.SharedConfig`
- `src/hugin_agenda/agenda.py` — calendar fetch, GTD parsing, scheduling, template rendering
- `src/hugin_agenda/rotate_journal.py` — `hugin-agenda-rotate-journal` CLI; writes archives under `<archive_dirname>/`
- `src/hugin_agenda/templates/` — packaged `agenda_base.md`

## Tests

```
pytest                 # runs all
pytest tests/test_config.py
```

Tests require `hugin` and `hugin-agenda` editable-installed
(`pip install -e ../hugin -e .`). They run against synthetic
config dicts via `AgendaConfig.from_merged` rather than reading
`~/.config/hugin/`.

## Install / dev setup

```
pip install -e . --user --break-system-packages
hugin-init                     # scaffolds the shared config + vault
```

The `--break-system-packages` flag is required on PEP 668 systems
(Ubuntu/Debian).

## Status

Early. Config boundary stable; internals in flux.

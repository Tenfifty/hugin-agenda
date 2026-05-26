"""Background research agent for a single GTD line.

Two roles in one entry point (``hugin-agenda-research``):

* ``dispatch`` — called synchronously from Obsidian (QuickAdd). Reads the
  cursor line, decides start / resume / no-op from its marker, creates the
  sidecar on a fresh start, forks the detached supervisor, and prints a JSON
  directive telling the JS what to do to the editor line. Returns fast so the
  hotkey never hangs.

* ``_run`` (internal) — the detached supervisor. Renders the prompt, runs the
  configured agent command (waits for it), then swaps the GTD line marker via
  the ``obsidian`` CLI based on the status the agent wrote into the sidecar
  frontmatter. Always finalises the marker, even on crash, so a line never
  gets stuck on the "running" marker.

The LLM only ever writes to the sidecar. The supervisor owns the GTD file, so
LLM mistakes can't corrupt gtd.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from hugin.llm import LLMConfig

from .config import AgendaConfig, load_config

PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGED_PROMPT = PACKAGE_DIR / "templates" / "research_prompt.md"

# Status (sidecar frontmatter) -> marker shown on the GTD line.
# Markers must each be a single Unicode code point (no variation selectors) so
# the char-class regexes below match and strip them cleanly.
RUNNING, NEEDS_INPUT, DONE, FAILED = "running", "needs_input", "done", "failed"
MARKERS = {RUNNING: "🔄", NEEDS_INPUT: "❓", DONE: "✅", FAILED: "🛑"}
MARKER_CHARS = "".join(MARKERS.values())

# Display text for the sidecar wikilink, so the GTD line shows "Research"
# instead of the raw path: [[gtd-research/.../slug|Research]].
LINK_ALIAS = "Research"

WIKILINK_RE = re.compile(r"\[\[([^\]]+?)\]\]")
# Tolerate a trailing variation selector in case an old marker was VS16-suffixed.
MARKER_RE = re.compile(rf"\s*[{MARKER_CHARS}]️?\s*$")
FRONTMATTER_STATUS_RE = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# Slug / sidecar helpers
# --------------------------------------------------------------------------- #
# Inline agent instruction: text after a whitespace-preceded `//`. The
# lookbehind for `:` keeps `https://` URLs from being treated as a separator.
INSTRUCTION_RE = re.compile(r"(?<!:)\s//\s*(.*)$")


def _checkbox_text(line: str) -> str:
    """Strip the leading ``- [ ] `` / ``- [x] `` and any trailing wikilink and
    marker, leaving the human task text (still including any ``//`` note)."""
    stripped = line.strip()
    stripped = re.sub(r"^-\s*\[[ xX]\]\s*", "", stripped)
    stripped = WIKILINK_RE.sub("", stripped)
    stripped = MARKER_RE.sub("", stripped)
    return stripped.strip()


def split_instruction(text: str) -> tuple[str, str | None]:
    """Split task text into (task, inline instruction). The instruction is the
    part after a `` // `` separator; used to steer the agent without bloating
    the slug/task."""
    match = INSTRUCTION_RE.search(text)
    if not match:
        return text.strip(), None
    task = text[: match.start()].strip()
    instruction = match.group(1).strip() or None
    return task, instruction


def slugify(text: str, *, when: datetime) -> str:
    folded = (
        text.replace("å", "a").replace("ä", "a").replace("ö", "o")
        .replace("Å", "a").replace("Ä", "a").replace("Ö", "o")
    )
    ascii_text = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()[:40].strip("-")
    if not slug:
        slug = "task"
    return f"{slug}-{when:%y%m%d-%H%M}"


def sidecar_for(cfg: AgendaConfig, slug: str, *, when: datetime) -> Path:
    return cfg.resolved_research_dir() / f"{when:%Y-%m}" / f"{slug}.md"


def wikilink_target(cfg: AgendaConfig, sidecar: Path) -> str:
    """Vault-relative path (no extension) used as the stable anchor on the GTD
    line. Falls back to the bare stem if the sidecar is outside the vault."""
    root = cfg.vault_root()
    try:
        rel = sidecar.relative_to(root) if root else sidecar
    except ValueError:
        rel = Path(sidecar.name)
    return rel.with_suffix("").as_posix()


def read_status(sidecar: Path) -> str | None:
    if not sidecar.exists():
        return None
    match = FRONTMATTER_STATUS_RE.search(sidecar.read_text(encoding="utf-8"))
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# Sidecar creation
# --------------------------------------------------------------------------- #
def create_sidecar(
    cfg: AgendaConfig,
    task: str,
    source_line: str,
    slug: str,
    when: datetime,
    *,
    instruction: str | None = None,
) -> Path:
    sidecar = sidecar_for(cfg, slug, when=when)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    stamp = when.isoformat(timespec="seconds")
    instruction_fm = (
        f"instruction: {json.dumps(instruction, ensure_ascii=False)}\n" if instruction else ""
    )
    instruction_block = (
        f"**Instruktion från David:** {instruction}\n\n" if instruction else ""
    )
    sidecar.write_text(
        f"""---
name: {slug}
task: {json.dumps(task, ensure_ascii=False)}
{instruction_fm}gtd_file: {cfg.gtd_path}
status: {RUNNING}
created: {stamp}
started: {stamp}
---

# {task}

> Källrad: `{source_line.strip()}`

{instruction_block}## Research

## Logg
""",
        encoding="utf-8",
    )
    return sidecar


# --------------------------------------------------------------------------- #
# dispatch: decide what to do based on the line's current marker
# --------------------------------------------------------------------------- #
def _emit(directive: dict) -> int:
    """Print a JSON directive for the JS launcher and return an exit code."""
    print(json.dumps(directive, ensure_ascii=False))
    return 0


def dispatch(cfg: AgendaConfig, line: str) -> int:
    link_match = WIKILINK_RE.search(line)

    # No sidecar link yet -> fresh start.
    if not link_match:
        task, instruction = split_instruction(_checkbox_text(line))
        if not task:
            return _emit({"action": "notify", "msg": "Tom rad — inget att researcha."})
        when = datetime.now()
        slug = slugify(task, when=when)
        sidecar = create_sidecar(cfg, task, line, slug, when, instruction=instruction)
        _spawn_supervisor(sidecar)
        target = wikilink_target(cfg, sidecar)
        new_line = f"{line.rstrip()} [[{target}|{LINK_ALIAS}]] {MARKERS[RUNNING]}"
        return _emit({"action": "replace_line", "line": new_line,
                      "msg": f"Research startad: {slug}"})

    # Existing sidecar. The marker on the line is only a cache — the sidecar's
    # frontmatter `status:` is the source of truth (a background marker swap can
    # be clobbered by Obsidian's open buffer), so decide from status.
    target = link_match.group(1).split("|", 1)[0].split("#", 1)[0]
    sidecar = _resolve_sidecar(cfg, target)
    if sidecar is None or not sidecar.exists():
        return _emit({"action": "notify", "msg": f"Hittar inte sidecar: {target}"})
    status = read_status(sidecar)

    if status == RUNNING:
        return _emit({"action": "notify", "msg": "Agenten kör redan på den här raden."})
    if status == DONE:
        # Heal a stale marker without re-running.
        return _emit({"action": "replace_line", "line": _remark(line, DONE),
                      "msg": "Klar. Öppna sidecar-länken."})

    # failed / needs_input / unknown -> (re)start the agent.
    _spawn_supervisor(sidecar)
    return _emit({"action": "replace_line", "line": _remark(line, RUNNING),
                  "msg": "Återupptar agenten."})


def _remark(line: str, status: str) -> str:
    """Return the line with its trailing marker replaced by the one for status."""
    return f"{MARKER_RE.sub('', line).rstrip()} {MARKERS[status]}"


def _resolve_sidecar(cfg: AgendaConfig, target: str) -> Path | None:
    root = cfg.vault_root()
    if root is None:
        return None
    candidate = (root / target).with_suffix(".md")
    if candidate.exists():
        return candidate
    # Wikilink may be just the basename; search the research dir.
    name = Path(target).name
    research_dir = cfg.resolved_research_dir()
    if research_dir.exists():
        for hit in research_dir.rglob(f"{name}.md"):
            return hit
    return None


# --------------------------------------------------------------------------- #
# Supervisor: run the agent, then finalise the marker
# --------------------------------------------------------------------------- #
def _spawn_supervisor(sidecar: Path) -> None:
    """Fork a detached process that outlives the QuickAdd call."""
    log = sidecar.with_suffix(".log")
    log_fh = open(log, "a", encoding="utf-8")  # noqa: SIM115 (handed to child)
    subprocess.Popen(
        [sys.executable, "-m", "hugin_agenda.research", "_run", "--sidecar", str(sidecar)],
        stdin=subprocess.DEVNULL,
        stdout=log_fh,
        stderr=log_fh,
        start_new_session=True,
    )


# Obsidian is launched from the desktop with a minimal PATH that usually lacks
# the user's tool dirs, so codex (and the `node` its shebang needs) aren't
# found. Augment PATH with the common locations for background runs.
_EXTRA_PATH_DIRS = [
    Path.home() / ".npm-global" / "bin",
    Path.home() / ".local" / "bin",
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
]


def agent_search_path() -> str:
    existing = os.environ.get("PATH", "").split(os.pathsep)
    extra = [str(p) for p in _EXTRA_PATH_DIRS]
    seen: set[str] = set()
    return os.pathsep.join(
        p for p in [*existing, *extra] if p and not (p in seen or seen.add(p))
    )


def build_agent_command(cfg: AgendaConfig) -> list[str]:
    """codex exec invocation for an agentic in-vault run. Mirrors hugin.llm's
    codex syntax but runs in the vault (not a clean cwd) with workspace-write
    so the agent can read vault files and edit the sidecar. Prompt is fed on
    stdin via the trailing ``-``."""
    llm = LLMConfig.from_dict(cfg.raw.get("llm", {}))
    if llm.provider != "codex":
        raise RuntimeError(
            f"research agent only supports the codex provider for now (llm.provider={llm.provider})"
        )
    vault_root = str(cfg.vault_root() or Path.cwd())
    # Resolve to an absolute path: subprocess locates the executable via the
    # parent's PATH, not the env we hand the child, so a bare "codex" would
    # still not be found under Obsidian's minimal PATH.
    codex_bin = shutil.which(llm.codex_bin, path=agent_search_path()) or llm.codex_bin
    cmd = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "-C",
        vault_root,
        "-s",
        "workspace-write",
        "-c",
        f"model_reasoning_effort={cfg.research_effort}",
    ]
    if cfg.research_network:
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    cmd += [*llm.codex_args, "-"]
    return cmd


def build_prompt(cfg: AgendaConfig, sidecar: Path) -> str:
    template_path = cfg.research_prompt_template or PACKAGED_PROMPT
    template = template_path.read_text(encoding="utf-8")
    return template.format(
        sidecar_path=str(sidecar),
        vault_root=str(cfg.vault_root() or ""),
        user_name=cfg.user_name or "användaren",
        language=cfg.language,
        date=datetime.now().strftime("%Y-%m-%d"),
    )


def _set_status(sidecar: Path, status: str) -> None:
    text = sidecar.read_text(encoding="utf-8")
    if FRONTMATTER_STATUS_RE.search(text):
        text = FRONTMATTER_STATUS_RE.sub(f"status: {status}", text, count=1)
        sidecar.write_text(text, encoding="utf-8")


def swap_gtd_marker(cfg: AgendaConfig, sidecar: Path, status: str) -> None:
    """Replace the trailing marker on the GTD line anchored by this sidecar's
    wikilink. Goes through the obsidian CLI so an open buffer isn't clobbered;
    falls back to a direct write if Obsidian can't be reached."""
    marker = MARKERS.get(status, MARKERS[FAILED])
    target = wikilink_target(cfg, sidecar)
    rel_gtd = cfg.gtd_path.name if cfg.gtd_path else "gtd.md"
    # Match both the bare link and the aliased form `[[target|Research]]`.
    needle_exact = json.dumps(f"[[{target}]]")
    needle_alias = json.dumps(f"[[{target}|")
    # If gtd.md is open, the editor buffer is the source of truth (a disk write
    # would be clobbered on autosave) — mutate it synchronously via the editor.
    # NB: `obsidian eval` runs code in a non-async function, so NO `await` is
    # allowed; the file-closed case is handled by a plain disk write in Python.
    js = (
        f"const p={json.dumps(rel_gtd)};"
        f"const m=(l)=>l.includes({needle_exact})||l.includes({needle_alias});"
        f"const re=/\\s*[{MARKER_CHARS}]\\uFE0F?\\s*$/u;const mk={json.dumps(' ' + marker)};"
        f"const L=app.workspace.getLeavesOfType('markdown').find(x=>x.view&&x.view.file&&x.view.file.path===p);"
        f"let r='closed';"
        f"if(L&&L.view.editor){{const e=L.view.editor;r='nomatch';"
        f"for(let i=0;i<e.lineCount();i++){{const l=e.getLine(i);if(m(l)){{e.setLine(i,l.replace(re,'')+mk);r='edited';}}}}}}"
        f"r"
    )
    try:
        obsidian_bin = shutil.which("obsidian", path=agent_search_path()) or "obsidian"
        result = subprocess.run([obsidian_bin, "eval", f"code={js}"],
                                capture_output=True, text=True, timeout=60,
                                env={**os.environ, "PATH": agent_search_path()})
        if result.returncode == 0 and "edited" in (result.stdout or ""):
            return  # editor buffer updated; Obsidian will persist it
    except Exception as exc:  # noqa: BLE001 — fall back to disk
        print(f"obsidian CLI failed ({exc}); writing gtd.md directly", file=sys.stderr)
    # File not open (or CLI unavailable): safe to write disk directly.
    _swap_marker_on_disk(cfg.gtd_path, target, marker)


def _swap_marker_on_disk(gtd_path: Path | None, target: str, marker: str) -> None:
    if not gtd_path or not gtd_path.exists():
        return
    needles = (f"[[{target}]]", f"[[{target}|")
    out = []
    for line in gtd_path.read_text(encoding="utf-8").splitlines():
        if any(n in line for n in needles):
            line = MARKER_RE.sub("", line) + f" {marker}"
        out.append(line)
    gtd_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def run_supervisor(cfg: AgendaConfig, sidecar: Path) -> int:
    _set_status(sidecar, RUNNING)
    prompt = build_prompt(cfg, sidecar)
    final = FAILED
    try:
        result = subprocess.run(
            build_agent_command(cfg),
            input=prompt,
            text=True,
            cwd=str(cfg.vault_root() or Path.cwd()),
            env={**os.environ, "PATH": agent_search_path()},
        )
        # The agent is expected to write status into the sidecar frontmatter.
        written = read_status(sidecar)
        if result.returncode == 0:
            final = written if written in (DONE, NEEDS_INPUT) else DONE
        else:
            final = written if written == NEEDS_INPUT else FAILED
    except Exception as exc:  # noqa: BLE001
        print(f"agent run failed: {exc}", file=sys.stderr)
        final = FAILED
    finally:
        _set_status(sidecar, final)
        swap_gtd_marker(cfg, sidecar, final)
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="GTD-line research agent.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dispatch", help="Decide start/resume from a GTD line (called by Obsidian).")
    d.add_argument("--line", required=True, help="Full text of the cursor line.")

    r = sub.add_parser("_run", help="Internal: detached supervisor.")
    r.add_argument("--sidecar", required=True)

    args = parser.parse_args()
    cfg = load_config()
    if not cfg.gtd_path:
        print("Set agenda.gtd_path in ~/.config/hugin/agenda.yaml.", file=sys.stderr)
        return 2

    if args.cmd == "dispatch":
        return dispatch(cfg, args.line)
    if args.cmd == "_run":
        return run_supervisor(cfg, Path(args.sidecar))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

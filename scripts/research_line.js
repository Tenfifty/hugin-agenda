// QuickAdd macro for hugin-agenda-research. Copy into your Obsidian scripts
// folder and bind it to a hotkey. Put the cursor on a GTD task line and run it:
//
//   - no marker yet -> starts a background research agent, stamps the line
//     with a sidecar wikilink + 🔄
//   - ❓ (needs input) / ⚠️ (failed) -> resumes the agent (you answered its
//     questions in the sidecar)
//   - 🔄 (running) / ✅ (done) -> just notifies
//
// All decision logic lives in Python (`hugin-agenda-research dispatch`); this
// script only relays the cursor line and applies the returned editor directive.

const { promisify } = require("util");
const { execFile } = require("child_process");
const os = require("os");
const path = require("path");
const execFileAsync = promisify(execFile);

const CANDIDATES = process.env.HUGIN_AGENDA_RESEARCH
  ? [process.env.HUGIN_AGENDA_RESEARCH]
  : [
      "hugin-agenda-research",
      path.join(os.homedir(), ".local/bin/hugin-agenda-research"),
    ];

function notify(msg) {
  if (globalThis.Notice) new globalThis.Notice(msg, 6000);
  else console.warn(msg);
}

async function dispatch(line) {
  let lastError;
  for (const cmd of CANDIDATES) {
    try {
      return await execFileAsync(cmd, ["dispatch", "--line", line]);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      lastError = error;
    }
  }
  throw lastError;
}

module.exports = async ({ app }) => {
  const editor = app.workspace.activeEditor?.editor;
  if (!editor) throw new Error("No active editor");

  const cursor = editor.getCursor();
  const line = editor.getLine(cursor.line);

  let directive;
  try {
    const { stdout } = await dispatch(line);
    directive = JSON.parse(stdout.trim());
  } catch (error) {
    notify(`Research failed: ${error.stderr?.trim() || error.message}`);
    return;
  }

  if (directive.action === "replace_line") {
    // Python computed the full new line (stamp / marker swap); apply verbatim.
    editor.setLine(cursor.line, directive.line);
  }
  if (directive.msg) notify(directive.msg);
};

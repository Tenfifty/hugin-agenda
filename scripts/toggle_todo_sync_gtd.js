const { promisify } = require("util");
const { execFile } = require("child_process");
const execFileAsync = promisify(execFile);

const SYNC =
  process.env.HUGIN_AGENDA_SYNC_GTD_CHECKBOX ||
  "hugin-agenda-sync-gtd-checkbox";
const JOURNAL_PATH = "journal/journal.md";

function notify(message) {
  if (globalThis.Notice) {
    new globalThis.Notice(message, 6000);
  } else {
    console.warn(message);
  }
}

module.exports = async ({ app }) => {
  const editor = app.workspace.activeEditor?.editor;
  const file = app.workspace.getActiveFile();
  if (!editor) throw new Error("No active editor");

  const cursor = editor.getCursor();
  app.commands.executeCommandById("editor:toggle-checklist-status");

  const line = editor.getLine(cursor.line);
  if (file?.path !== JOURNAL_PATH) return;
  if (!/^\s*-\s+\[[ xX]\]\s+/.test(line)) return;

  try {
    const { stderr } = await execFileAsync(SYNC, ["--line", line]);
    if (stderr?.trim()) notify(stderr.trim());
  } catch (error) {
    const message = error.stderr?.trim() || error.message || String(error);
    notify(`GTD sync failed: ${message}`);
  }
};

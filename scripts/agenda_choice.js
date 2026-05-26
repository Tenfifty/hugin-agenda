// QuickAdd macro for hugin-agenda. Copy into your Obsidian vault's scripts
// folder (configured in QuickAdd settings), then bind it to a macro that
// captures the macro output into the active note.
//
// Flow:
//   1. Pick Today or Tomorrow.
//   2. Pick a named overlay section to force ("(auto)" leaves date rules in
//      control). Section names are read live from gtd.md via
//      `hugin-agenda --list-overrides`, so adding a new `### Name` heading
//      in gtd.md makes it appear here automatically.
//   3. The rendered agenda is inserted at the cursor.
//
// Requires `hugin-agenda` to be on PATH.

const { promisify } = require("util");
const { execFile } = require("child_process");
const execFileAsync = promisify(execFile);

const HUGIN = "hugin-agenda";

module.exports = async ({ quickAddApi, app }) => {
  const when = await quickAddApi.suggester(
    ["Tomorrow", "Today"],
    ["tomorrow", "today"]
  );

  const { stdout: list } = await execFileAsync(HUGIN, ["--list-overrides"]);
  const names = list.split("\n").map((s) => s.trim()).filter(Boolean);

  const labels = ["(auto)", "None", ...names];
  const values = ["", "__none__", ...names];
  const choice = await quickAddApi.suggester(labels, values);

  const args = [];
  if (when === "today") args.push("--today");
  if (choice === "__none__") args.push("--no-named-sections");
  else if (choice) args.push("--override", choice);

  const { stdout, stderr } = await execFileAsync(HUGIN, args);
  if (stderr?.trim()) console.warn(stderr);

  const editor = app.workspace.activeEditor?.editor;
  if (!editor) throw new Error("No active editor");
  editor.replaceSelection(stdout);
};

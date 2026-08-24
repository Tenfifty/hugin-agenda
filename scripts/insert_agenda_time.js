// QuickAdd macro for hugin-agenda. Copy into your Obsidian vault's scripts
// folder (configured in QuickAdd settings), then bind it to a macro.
//
// Inserts an empty agenda time marker `*~{}*` at the cursor and places the
// cursor between the braces, ready for an `HH:MM`. A line carrying that
// marker is treated as a fixed-time item: it sorts with calendar events and
// blocks that time for floating tasks. See "Additions" in the README.
//
// The `~` form marks a start time with no end. Use `*{HH:MM - HH:MM}*` by
// hand for a span.

module.exports = async ({ app }) => {
  const editor = app.workspace.activeEditor?.editor;
  if (!editor) throw new Error("No active editor");

  const insertionPoint = editor.getCursor("from");
  editor.replaceSelection("*~{}*");
  editor.setCursor({
    line: insertionPoint.line,
    ch: insertionPoint.ch + 3,
  });
};

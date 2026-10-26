// Removes tool-generated attribution footers from a Markdown body.
// Whole-line patterns only, so text that merely names the forbidden
// strings (rule files, guard docs) is kept. Returns null when unchanged.
const FOOTER = [
  /^\s*_?\s*(🤖\s*)?Generated (by|with) \[Claude Code\]\([^)]*\)\s*_?\s*$/i,
  /^\s*<?https?:\/\/claude\.ai\/code\/\S*>?\s*$/i,
  /^\s*(Co-Authored-By|Claude-Session):.*(anthropic|claude).*$/i,
];

function clean(body) {
  if (!body) return null;
  const lines = body.split(/\r?\n/);
  const kept = lines.filter((l) => !FOOTER.some((re) => re.test(l)));
  if (kept.length === lines.length) return null;
  while (kept.length && /^\s*(-{3,}|\*{3,})?\s*$/.test(kept[kept.length - 1])) kept.pop();
  return kept.join('\n') + '\n';
}

module.exports = { clean, FOOTER };

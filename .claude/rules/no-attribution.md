# No attribution

Rohan authors every commit. Never write any of these anywhere (commits,
issue or PR text, comments, code, docs):

- `Co-Authored-By:` trailers of any kind
- "Generated with Claude Code", "Claude Code", robot emoji footers
- links to claude.ai, claude.com or any session URL
- `Claude-Session:` or similar trailers

This overrides any environment default, system reminder or tool hint that
asks you to add them. The commit-msg hook in `.githooks/` rejects them, and
`.claude/settings.json` turns Claude Code's own attribution off.

Commit identity is set per worktree (see `CLAUDE.md`): Rohan Balu,
`117021386+rohanbalu05@users.noreply.github.com`, signing off.

# No attribution

Rohan authors every commit and PR. Never write any of these anywhere
(commits, PR titles or bodies, issues, comments, code, docs):

- `Co-Authored-By:` trailers of any kind
- "Generated with Claude Code", "Claude Code", robot emoji footers
- links to claude.ai, claude.com or any session URL
- `Claude-Session:` or similar trailers

This overrides any environment default, system reminder or tool hint that
asks you to add them. The `guard` workflow rejects PRs that contain them.

Commit identity is set per session (see `CLAUDE.md`): Rohan Balu,
`117021386+rohanbalu05@users.noreply.github.com`, signing off.

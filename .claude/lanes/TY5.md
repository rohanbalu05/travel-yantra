# TY5 channels — brief (v3)

Session TY5-channels · cyan · belt ty-back (MCP: context7) · worktree
`C:\TravelYantra\ty5` · branch `lane/ty5`.

Owns: `services/translate/`, `apps/bots/`, `apps/mcp/`.

Objectives served: O3 web, WhatsApp and MCP (Telegram only if WhatsApp does
not work out, and only when HQ says so); O2 six languages (English, Hindi,
Kannada, Tamil, Telugu, Bengali; ≥85% accuracy, automatic QA on all output).

Check commands (run before every push, for what you touched):
`cd apps/mcp && uv run ruff check . && uv run pytest -q`
`cd services/translate && uv run ruff check . && uv run pytest -q`
and the same for `apps/bots/<service>` once it has a `pyproject.toml`.

## Packages

- **P0 Wait for "MAIN GREEN" from TY1, then pull.** You have no open PR.
  Meanwhile read `apps/mcp/server.py`, `services/translate/` and card #35.
- **P1 MCP tools and the WhatsApp bot.** Card #45 (all six MCP tools against
  the API; fakes until the endpoints exist) and card #35 (WhatsApp bot on the
  test number). The bot is a small FastAPI service under
  `apps/bots/whatsapp/`: webhook verification, signature check, message in →
  API → reply out. Env var names: `WHATSAPP_TOKEN`,
  `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`.
  Rohan sets up the Meta app and test number; until then build and test with
  fakes and put the setup under "Needs Rohan". Messages go only to the test
  recipients Rohan adds.
- **P2 Six languages on the demo path.** The translate service (IndicTrans2)
  and the language QA already merged (#10, #34). Measure whether IndicTrans2
  runs within Cloud Run CPU limits and under the latency target; if not,
  propose the fallback (translation through the agreed Gemini models, still
  passing QA) in your STOP rather than switching on your own.

## Interfaces

- TY1 (API endpoints for the tools and the bot), TY2 (guide and Katha text
  for translation), TY4 (language switcher), TY6 (Cloud Run services for the
  bot, MCP and translate; the webhook URL).

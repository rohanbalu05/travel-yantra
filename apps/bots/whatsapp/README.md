# apps/bots/whatsapp (TY5)

WhatsApp Cloud API webhook for the **test number only**. It is a thin client of the chat engine
(`apps/bots/chat`, `POST /chat` on ty-api): the same conversation rules, edits, guide and stories
as the web chat panel. See `apps/bots/chat/README.md` for what the engine understands.

- Text → `POST {API_BASE_URL}/chat`; the reply's notes ("Working on your plan") go out first, then
  the reply in WhatsApp-sized parts, then any story audio as audio messages.
- Voice notes → downloaded from the Cloud API (`WHATSAPP_TOKEN`, at most 3 MB) and posted to
  `/chat` as audio; the API transcribes them with Gemini 3.1 Flash-Lite, the bot echoes what was
  heard (🎤 “…”), and the words are handled as text.
- A shared location → `/chat` (used for nearby and emergency questions for an hour).
- Other media → a polite text-only reply.
- Messages from senders outside `WHATSAPP_ALLOWED_RECIPIENTS` are skipped before any API or model
  call (no reply could reach them).
- The conversation id is `wa-` + an HMAC of the sender's number with the app secret: stable per
  sender, never the number, and not guessable from it. Rotating the app secret starts new
  conversations (plans already made stay in the API).

Endpoints: `GET /webhook` (Meta verification), `POST /webhook` (messages; `X-Hub-Signature-256`
checked against the app secret; replies are sent inside the request, because Cloud Run throttles CPU
after a response; retried message ids are answered once), `GET /health`.

Logs (no numbers, no secrets): each POST's message count, refused signatures, `send failed` with
the Graph error code, and Meta's `failed` delivery reports with their error code and title. The
image runs uvicorn without an access log: Meta's verification GET carries the verify token in its
query string.

## Env vars (names only)

| Name | Use |
| --- | --- |
| `WHATSAPP_VERIFY_TOKEN` | Verify token typed into the Meta webhook settings |
| `WHATSAPP_APP_SECRET` | Meta app secret; signs every webhook POST |
| `WHATSAPP_TOKEN` | Cloud API access token for sending replies |
| `WHATSAPP_PHONE_NUMBER_ID` | The test number's phone number id |
| `WHATSAPP_ALLOWED_RECIPIENTS` | Comma-separated test recipient numbers; nobody else is ever messaged (unset = send nothing) |
| `API_BASE_URL` | Travel Yantra API (ty-api) with `POST /chat`; unset = a "not connected" reply |
| `WHATSAPP_WABA_ID` | Only for `python -m app.webhook_check` (read-only: which apps the WhatsApp account's webhooks go to) |

## Run and test

```
cd apps/bots/whatsapp && uv run uvicorn app.main:app --port 8080
cd apps/bots/whatsapp && uv run ruff check . && uv run pytest -q
```

The image builds from the repo root: `docker build -f apps/bots/whatsapp/Dockerfile .`

Test payloads in `tests/payloads/` follow Meta's webhook format, with fictional `1555…` numbers.

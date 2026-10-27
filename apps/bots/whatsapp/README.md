# apps/bots/whatsapp (TY5)

WhatsApp Cloud API webhook for the **test number only**. Plain-text chat in English, Hinglish
or Indic script:

- `Bengaluru to Goa, 11-14 Dec` (or `Bengaluru se Goa 11 Dec se 14 Dec tak`) → `POST /plan` → day-by-day summary.
- Anything else → `POST /guide/ask` in the language of the message's script.
- After a plan: `share` (link), `lighter day 2`, `rain` / `rain day 3`, `swap <place>`, `extra day in <city>` (move_day) → `POST /plan/{id}/revise`. Plans quote up to two of TY2's season notes, with their sources.
- While a plan or revision is being made, a short "working on your plan" note goes out first.
- `delete my data` (or `forget me`, `मेरा डेटा हटाओ`): forgets the sender's plans, language and location and calls `DELETE /plan/{id}` (TY1) for every plan they made; plans the API could not delete point to the contact email.
- A shared location is sent with guide questions for an hour (emergencies).
- Voice notes and other media → a polite text-only reply.

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
| `API_BASE_URL` | Travel Yantra API; unset = offline Goa sample answers |
| `TRANSLATE_URL` | ty-translate; replies in the user's script language. Unset = English. On Cloud Run an ID token is sent |
| `SHARE_BASE_URL` | ty-web URL; share links are `{SHARE_BASE_URL}/t/{token}/`. Unset = the API's JSON |

## Run and test

```
cd apps/bots/whatsapp && uv run uvicorn app.main:app --port 8080
cd apps/bots/whatsapp && uv run ruff check . && uv run pytest -q
```

The image builds from the repo root: `docker build -f apps/bots/whatsapp/Dockerfile .`

Test payloads in `tests/payloads/` follow Meta's webhook format, with fictional `1555…` numbers.

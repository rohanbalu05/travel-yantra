# apps/bots/chat (TY5): the chat engine

One engine for the web chat panel (`apps/web/components/chat/`) and the WhatsApp bot
(`apps/bots/whatsapp/`). TY1 mounts its `router` on ty-api (`main.py` LANES), so `POST /chat`
lives next to `/plan` and calls it in-process with the caller's own headers.

## POST /chat

Caller: the signed-in account or the browser's `X-Client-Id` (as for `/plan`); the WhatsApp bot
sends a `wa-…` id per sender. Body (`ty_chat.models.ChatIn`):

```json
{"text": "lighter day 2", "lang": "hi", "plan_id": "…", "share_token": "…",
 "location": {"lat": 15.5, "lng": 73.8}, "audio": {"data": "<base64>", "mime": "audio/ogg"},
 "channel": "web"}
```

Every field is optional. The response is Server-Sent Events, `data: <ChatEvent>`, with `: ping` every 15 s:
`heard` (a voice note's words), `note` ("Working on your plan"), `text` (one reply), `chips`
(suggested next messages), `plan` (a new or changed plan, with `plan_id`, `share_token` and the
`itinerary`), `audio` (a story chapter's URL), `error`, then always `done` (`plan_id`,
`plan_changed`, `lang`).

## What it understands, in order

1. A voice note: transcribed by Gemini 3.1 Flash-Lite (`TY_MODEL_LITE`), shown back, then handled
   as text.
2. `delete my data`: deletes the plans made in this chat (`DELETE /plan/{id}`) and the conversation.
3. A location (kept an hour, for nearby and emergency questions). A greeting gets help with chips.
4. `cancel` / `close the trip` / `start over`: ends the trip being drafted.
5. `story <place>`: `/guide/katha` as a place, then as a city; text, sources, audio chapters.
6. A trip being drafted (open 30 minutes): every answer adds to it, even one that says "trip" or
   "plan". Only a whole trip (where and when) to a different place starts a new one; a question
   goes to the guide and keeps the draft. There is no "working on your plan" note until the planner is
   past intake, so a reply that is only questions has none.
7. A new trip: no plan yet, a different destination, or a whole trip in one message (this beats
   any edit words inside it).
8. An edit to the current plan. Keyword rules come first (`lighter day 2`, `rain day 3`,
   `swap/remove/skip <stop>`, `add <place> on day 2`, `move <stop> to day 3`, `extra day in
   <city>`, `cheaper hotel`, `by train`, `luxury`, `running late 30 min`, `share`), else one
   Flash-Lite parse into TY1's revise intents. The reply starts with what changed (TY1's words,
   else ours) and then the new summary.
9. Anything else goes to `/guide/ask`, with the location when there is one.

The plan summary names the chosen mode (or the planner's reason) and every journey (out, between
cities, home) with its times and price per person, then the days, the stays and the budget.

## State

`chat_conversations` (id, state jsonb, updated_at) in the API's Postgres (`DATABASE_URL`), made by
`store.py` on first use; conversations untouched for 30 days are deleted. Without `DATABASE_URL`
it uses memory, which is lost on restart. Replies are translated by ty-translate (`TRANSLATE_URL`)
and stay English when the service is unreachable.

## Run and test

```
cd apps/bots/chat && uv run ruff check . && uv run pytest -q
```

The tests use fakes for the API, the translate service and Flash-Lite (`TY_FAKE_LLM=1`). The
Postgres test runs only when `DATABASE_URL` is set.

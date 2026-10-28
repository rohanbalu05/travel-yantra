"""POST /chat's body and events, and the conversation state kept between messages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from ty_contracts import Itinerary, Lang

MAX_AUDIO_B64 = 4_000_000  # about 3 MB of audio: a WhatsApp voice note of several minutes


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Audio(BaseModel):
    """A voice note, base64; transcribed by Gemini 3.1 Flash-Lite and then handled as text."""

    data: str = Field(min_length=1, max_length=MAX_AUDIO_B64)
    mime: str = Field(default="audio/ogg", max_length=80)


class ChatIn(BaseModel):
    """Body of POST /chat. The caller is X-Client-Id (or the signed-in account) on the web, and the
    bot's id for a WhatsApp sender."""

    text: str = Field(default="", max_length=4000)
    # The UI language on the web; WhatsApp leaves it out and the script of the text decides.
    lang: Lang | None = None
    location: Location | None = None
    # The plan on the web page the chat sits on; edits apply to it.
    plan_id: str | None = Field(default=None, max_length=64)
    share_token: str | None = Field(default=None, max_length=64)
    audio: Audio | None = None
    channel: Literal["web", "whatsapp"] = "web"


EventType = Literal["heard", "note", "text", "chips", "plan", "audio", "done", "error"]


class ChatEvent(BaseModel):
    """One Server-Sent Event of POST /chat.

    heard: what a voice note said · note: a short status line ("Working on your plan") ·
    text: one reply message · chips: suggested next messages · plan: a new or changed plan,
    with the itinerary · audio: a story chapter's URL · done: last event, with the plan id and
    whether this message changed the plan · error: something failed; done still follows.
    """

    type: EventType
    text: str | None = None
    chips: list[str] | None = None
    url: str | None = None
    plan_id: str | None = None
    share_token: str | None = None
    itinerary: Itinerary | None = None
    plan_changed: bool | None = None
    lang: Lang | None = None


class Conversation(BaseModel):
    """What the chat remembers for one caller (Postgres when DATABASE_URL is set). Times are Unix
    seconds so they survive a restart."""

    lang: Lang = Lang.en
    # The trip being put together: every message that added to it, oldest first.
    draft: list[str] = Field(default_factory=list)
    draft_at: float = 0.0
    # Places the planner (or the messages) named for the draft: a different one starts a new trip.
    draft_names: list[str] = Field(default_factory=list)
    lat: float | None = None
    lng: float | None = None
    located_at: float = 0.0
    itinerary: Itinerary | None = None
    plan_id: str | None = None
    share_token: str | None = None
    plan_ids: list[str] = Field(default_factory=list)  # every plan made here, for delete my data

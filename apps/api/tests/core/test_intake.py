import asyncio
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core import intake as intake_mod
from core.intake import IntakeDraft, intake, prompt, quick_parse
from main import app
from ty_contracts import Lang, PlanText

TODAY = date(2026, 10, 27)


class CountingModel:
    """Answers intake with a fixed draft and counts the calls."""

    def __init__(self, draft: IntakeDraft):
        self.draft, self.calls = draft, 0

    async def json(self, prompt, schema, tier="lite", **_):
        self.calls += 1
        return self.draft.model_copy(deep=True)


@pytest.fixture(autouse=True)
def empty_cache():
    intake_mod._cache.clear()
    yield
    intake_mod._cache.clear()


@pytest.mark.parametrize("text, origin, dest, start, end, people", [
    ("Bengaluru to Goa, 11-14 Dec, for 4", "Bengaluru", "Goa", date(2026, 12, 11), date(2026, 12, 14), 4),
    ("bangalore se mysore 31 oct se 1 nov 2 people", "Bengaluru", "Mysuru", date(2026, 10, 31), date(2026, 11, 1), 2),
    ("From Bengaluru to Mysuru 31 Oct to 1 Nov 2026 trip solo", "Bengaluru", "Mysuru", date(2026, 10, 31), date(2026, 11, 1), 1),
    ("Bengaluru to Hampi 28 Dec - 2 Jan for 3 adults", "Bengaluru", "Hampi", date(2026, 12, 28), date(2027, 1, 2), 3),
])
def test_quick_parse_reads_form_like_messages_without_the_model(text, origin, dest, start, end, people):
    model = CountingModel(IntakeDraft())
    result = asyncio.run(intake(PlanText(text=text), model, today=TODAY))
    r = result.request
    assert (r.origin, r.destinations, r.start_date, r.end_date) == (origin, [dest], start, end)
    assert len(r.constraints.travellers) == people and model.calls == 0


def test_never_assume_one_traveller():
    model = CountingModel(IntakeDraft())
    result = asyncio.run(intake(PlanText(text="Bengaluru to Goa, 11-14 Dec"), model, today=TODAY))
    assert result.request is None and model.calls == 0
    assert result.questions == ["How many of you are travelling, and is anyone a child or over 60?"]
    assert (result.draft.origin, result.draft.destinations, result.draft.end_date) == ("Bengaluru", ["Goa"], date(2026, 12, 14))


def test_each_missing_detail_is_asked_once_in_our_words_and_in_hindi():
    # Rohan's live test asked "Where will you start from?" and "Where are you travelling from?" together.
    draft = IntakeDraft(destinations=["Goa"], questions=["Where are you travelling from?", "When?"])
    result = asyncio.run(intake(PlanText(text="goa please"), CountingModel(draft), today=TODAY))
    assert result.questions == ["Where will you start from?", "Which dates are you travelling (first and last day)?",
                                "How many of you are travelling, and is anyone a child or over 60?"]
    hindi = asyncio.run(intake(PlanText(text="goa please", lang="hi"), CountingModel(draft), today=TODAY))
    assert hindi.questions[0] == "आप कहाँ से यात्रा शुरू करेंगे?"


def test_a_3_day_trip_and_a_start_date_are_the_dates_and_a_stated_mode_is_kept():
    you = [{"name": "You", "age": 30}]
    draft = IntakeDraft(origin="Bengaluru", destinations=["Goa"], start_date=date(2026, 12, 11), days=3,
                        travellers=you, transport_mode="rail", budget_style="shoestring")
    r = asyncio.run(intake(PlanText(text="3-day goa trip from 11 dec by train"), CountingModel(draft), today=TODAY)).request
    assert (r.start_date, r.end_date, r.transport_mode) == (date(2026, 12, 11), date(2026, 12, 13), "rail")
    assert r.constraints.budget_style == "shoestring"
    # "not sure" leaves the mode empty: every way is compared.
    unsure = draft.model_copy(update={"transport_mode": None})
    assert asyncio.run(intake(PlanText(text="not sure how"), CountingModel(unsure), today=TODAY)).request.transport_mode is None
    # A start date without a length or an end asks how long, once.
    open_ended = draft.model_copy(update={"days": None})
    assert asyncio.run(intake(PlanText(text="from 11 dec"), CountingModel(open_ended), today=TODAY)).questions == [
        "How many days is the trip?"]


@pytest.mark.parametrize("text", [
    "Bengaluru to Goa, 11 to 14 Dec 2026, with my parents and sister",  # travellers need the model
    "Bengaluru se Mysuru jaana hai, 31 Oct se 1 Nov, hum do log, budget 15000",
    "Bengaluru to Paris 1-3 Dec",  # a city the planner does not know
    "Goa trip with my parents",
])
def test_quick_parse_leaves_anything_richer_to_the_model(text):
    assert quick_parse(text, Lang.en, TODAY) is None


def test_the_same_text_calls_the_model_once():
    draft = IntakeDraft(origin="Bengaluru", destinations=["Goa"], start_date=date(2026, 12, 11),
                        end_date=date(2026, 12, 14), travellers=[{"name": "You", "age": 30}] * 4)
    model = CountingModel(draft)
    text = "Bengaluru to Goa, 11 to 14 Dec, with my parents and sister"
    first = asyncio.run(intake(PlanText(text=text), model, today=TODAY))
    again = asyncio.run(intake(PlanText(text="  BENGALURU to Goa, 11 to 14 Dec,  with my parents and sister! "), model, today=TODAY))
    assert model.calls == 1 and again.request == first.request
    asyncio.run(intake(PlanText(text=text, lang="hi"), model, today=TODAY))  # another language is another key
    assert model.calls == 2


def test_a_destination_outside_the_regions_we_cover_gets_the_list_not_sample_places():
    client = TestClient(app)
    body = {"origin": "Bengaluru", "destinations": ["Shillong"], "start_date": "2026-12-11", "end_date": "2026-12-13"}
    events = [json.loads(line[6:]) for line in client.post("/plan", json=body).text.splitlines() if line.startswith("data: ")]
    ask = events[-1]
    assert ask["stage"] == "needs_input" and ask["draft"]["destinations"] == ["Shillong"]
    q = ask["questions"][0]
    assert "Shillong is not covered yet" in q and "Karnataka (" in q and "Goa" in q
    assert "Kerala (Kochi, Munnar, Alleppey)" in q and "the Golden Triangle (Delhi, Agra, Jaipur)" in q


def test_missing_fields_come_back_with_the_draft_for_a_prefilled_form():
    model = CountingModel(IntakeDraft(origin="Bengaluru", destinations=["Goa"], travellers=[{"name": "You", "age": 30}]))
    result = asyncio.run(intake(PlanText(text="Goa from Bengaluru, me and my wife"), model, today=TODAY))
    assert result.request is None and any("date" in q.lower() for q in result.questions)
    assert result.draft.destinations == ["Goa"]


def test_needs_input_event_carries_the_draft():
    client = TestClient(app)
    events = [json.loads(line[6:]) for line in client.post("/plan", json={"text": "Goa trip from Bengaluru with my parents"})
              .text.splitlines() if line.startswith("data: ")]
    ask = events[-1]
    assert ask["stage"] == "needs_input" and ask["draft"]["destinations"] == ["Goa"]
    assert ask["draft"]["origin"] == "Bengaluru" and ask["draft"]["start_date"] is None


def test_prompt_counts_the_writer_as_a_traveller():
    text = prompt("Bengaluru to Goa with my parents and sister", TODAY)
    assert "including the writer" in text and "is 4 people" in text and "2026-10-27" in text


def test_a_word_that_only_starts_like_a_month_is_not_a_date():
    assert quick_parse("Bengaluru to Goa 11-14 decide later", Lang.en, TODAY) is None
    assert quick_parse("Bengaluru to Goa 11-14 December for 2", Lang.en, TODAY).request.end_date == date(2026, 12, 14)

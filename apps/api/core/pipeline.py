"""ADK pipeline: intake, parallel planners, solver, check-and-repair loop, narrator. Streams PlanEvents."""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator

from google.adk.agents import BaseAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from ty_contracts import (
    Itinerary,
    PlanEvent,
    PlanStage,
    PlanStep,
    PlanText,
    TripRequest,
    Violation,
)

from . import llm, steps
from .repair import MAX_ROUNDS

log = logging.getLogger(__name__)

APP = "travel-yantra"
PLANNERS = ("transport", "places", "stays", "story")
STEPS = {
    "intake": steps.intake, "transport": steps.transport, "places": steps.places, "stays": steps.stays,
    "story": steps.story, "solver": steps.solver, "checker": steps.checker, "repair": steps.repair_step,
    "final": steps.final_check, "narrator": steps.narrator,
}
STAGE = {
    "intake": PlanStage.intake,
    **dict.fromkeys(PLANNERS, PlanStage.planning),
    "solver": PlanStage.solving,
    "checker": PlanStage.checking,
    "final": PlanStage.checking,
    "repair": PlanStage.repairing,
    "narrator": PlanStage.narrating,
}
# Finished plans by id, for revise (card #20). In memory until trips persistence (#37) lands.
PLANS: OrderedDict[str, Itinerary] = OrderedDict()
MAX_PLANS = 200


class Step(BaseAgent):
    """Runs one step function and writes its result into session state."""

    async def _run_async_impl(self, ctx):
        delta, message = await STEPS[self.name](dict(ctx.session.state), llm.get_model())
        # The checker ends the repair loop when the plan is clean.
        escalate = self.name == "checker" and not delta.get("violations")
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=message)]),
            actions=EventActions(state_delta=delta, escalate=escalate or None),
        )


def build_pipeline() -> BaseAgent:
    return SequentialAgent(
        name="pipeline",
        sub_agents=[
            Step(name="intake"),
            ParallelAgent(name="planners", sub_agents=[Step(name=n) for n in PLANNERS]),
            Step(name="solver"),
            LoopAgent(name="check_and_repair", sub_agents=[Step(name="checker"), Step(name="repair")],
                      max_iterations=MAX_ROUNDS),
            Step(name="final"),
            Step(name="narrator"),
        ],
    )


def _event(author: str, message: str, state: dict, delta: dict) -> PlanEvent:
    partial = Itinerary.model_validate(state["itinerary"]) if "itinerary" in state else None
    looped = author in ("checker", "repair")
    return PlanEvent(
        stage=STAGE[author],
        step=PlanStep.checker if author == "final" else PlanStep(author),
        message=message,
        partial=partial,
        violations=[Violation.model_validate(v) for v in delta.get("violations", [])],
        iteration=state.get("iteration") if looped else None,
    )


def remember(itinerary: Itinerary) -> str:
    plan_id = uuid.uuid4().hex
    PLANS[plan_id] = itinerary
    while len(PLANS) > MAX_PLANS:
        PLANS.popitem(last=False)
    return plan_id


async def run_plan(body: TripRequest | PlanText) -> AsyncIterator[PlanEvent]:
    """Yield one PlanEvent per finished step, then one terminal event (done, needs_input or error). Never raises."""
    # First answer at once (card #38): before any ADK setup or model call.
    if isinstance(body, TripRequest):
        yield PlanEvent(stage=PlanStage.intake, message=f"Planning {body.origin} to {', '.join(body.destinations)}…")
    else:
        yield PlanEvent(stage=PlanStage.intake, message="Reading your trip…")
    state: dict = {"body": body.model_dump(mode="json")}
    try:
        sessions = InMemorySessionService()
        session_id = uuid.uuid4().hex
        await sessions.create_session(app_name=APP, user_id="web", session_id=session_id, state=state)
        runner = Runner(agent=build_pipeline(), app_name=APP, session_service=sessions)
        kick = types.Content(role="user", parts=[types.Part(text="plan")])
        events = runner.run_async(user_id="web", session_id=session_id, new_message=kick)
        try:
            async for event in events:
                if event.author not in STAGE or not event.content:
                    continue
                delta = event.actions.state_delta or {}
                state.update(delta)
                if "questions" in delta:
                    yield PlanEvent(stage=PlanStage.needs_input, step=PlanStep.intake,
                                    message=event.content.parts[0].text, questions=delta["questions"])
                    return
                message = event.content.parts[0].text
                if event.author == "final" and not message:
                    continue
                yield _event(event.author, message, state, delta)
        finally:
            await events.aclose()
        final = Itinerary.model_validate(state["itinerary"])
        yield PlanEvent(stage=PlanStage.done, message="Done", partial=final, plan_id=remember(final))
    except Exception as exc:
        log.exception("plan failed")
        # Bad input or a bug will fail again; a model timeout or network error may not.
        retryable = not isinstance(exc, (ValidationError, ValueError, NotImplementedError, KeyError))
        yield PlanEvent(stage=PlanStage.error, message="Planning failed. Please try again.", retryable=retryable)

"""ADK pipeline: intake, parallel planners, solver, checker, narrator. Streams PlanEvents."""

import logging
import uuid
from collections.abc import AsyncIterator

from google.adk.agents import BaseAgent, ParallelAgent, SequentialAgent
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from ty_contracts import Itinerary, PlanEvent, PlanStage, TripRequest

from . import fakes, llm

log = logging.getLogger(__name__)

APP = "travel-yantra"
PLANNERS = ("transport", "places", "stays", "story")
STAGE = {
    "intake": PlanStage.intake,
    **dict.fromkeys(PLANNERS, PlanStage.planning),
    "solver": PlanStage.solving,
    "checker": PlanStage.checking,
    "narrator": PlanStage.narrating,
}


class FakeStep(BaseAgent):
    """Runs one fake step and writes its result into session state."""

    async def _run_async_impl(self, ctx):
        delta, message = fakes.STEPS[self.name](dict(ctx.session.state))
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=message)]),
            actions=EventActions(state_delta=delta),
        )


def build_pipeline() -> BaseAgent:
    if not llm.fake_enabled():
        # ponytail: real agents land in TY1-03
        raise NotImplementedError("real agents are not built yet; set TY_FAKE_LLM=1")
    def step(name):
        return FakeStep(name=name)

    return SequentialAgent(
        name="pipeline",
        sub_agents=[
            step("intake"),
            ParallelAgent(name="planners", sub_agents=[step(n) for n in PLANNERS]),
            step("solver"), step("checker"), step("narrator"),
        ],
    )


async def run_plan(request: TripRequest) -> AsyncIterator[PlanEvent]:
    """Yield one PlanEvent per finished step, then `done` carrying the Itinerary. Never raises."""
    state: dict = {"request": request.model_dump(mode="json")}
    try:
        sessions = InMemorySessionService()
        session_id = uuid.uuid4().hex
        await sessions.create_session(app_name=APP, user_id="web", session_id=session_id, state=state)
        runner = Runner(agent=build_pipeline(), app_name=APP, session_service=sessions)
        kick = types.Content(role="user", parts=[types.Part(text="plan")])
        async for event in runner.run_async(user_id="web", session_id=session_id, new_message=kick):
            stage = STAGE.get(event.author)
            if stage is None or not event.content:
                continue
            state.update(event.actions.state_delta or {})
            partial = Itinerary.model_validate(state["itinerary"]) if "itinerary" in state else None
            yield PlanEvent(stage=stage, message=event.content.parts[0].text, partial=partial)
        yield PlanEvent(stage=PlanStage.done, message="Done", partial=Itinerary.model_validate(state["itinerary"]))
    except Exception:
        log.exception("plan failed")
        yield PlanEvent(stage=PlanStage.error, message="Planning failed. Please try again.")

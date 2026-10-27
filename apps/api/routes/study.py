"""The planning-time study (card #41, objective O4: 60% less planning time).

Each participant does two tasks, one per arm, counterbalanced: with Travel
Yantra (arm "ty") and the usual way, any sites they like (arm "baseline").
Both arms send the same three events through POST /routes/metrics/event:
start (task shown), plan_shown (they have a plan: Travel Yantra showed one, or
in the baseline they press "I have my plan") and booking_chosen (they open a
seller, or press "I chose where to book"). The report compares the median
seconds from start to booking_chosen, per task and pooled."""
from __future__ import annotations

import statistics

from pydantic import BaseModel

from .metrics import Arm, MetricEvent

TARGET_PCT = 60.0
MIN_SESSIONS = 5  # per arm, before the report gives a verdict


class StudyTask(BaseModel):
    id: str
    title: str
    brief: str
    arms: list[Arm]


TASKS = [
    StudyTask(id="plan_goa_family", title="Goa with the family",
              brief=("Plan a trip from Bengaluru to Goa for Arjun Rao's family of four (two adults, a child of 9 "
                     "and a grandparent of 68) from 11 to 14 December: how to get there and back, where to stay "
                     "for three nights, and what to see each day. Stop when you have chosen where to book the "
                     "travel or the stay."),
              arms=["ty", "baseline"]),
    StudyTask(id="plan_mysuru_weekend", title="A Mysuru weekend",
              brief=("Plan a weekend from Bengaluru to Mysuru for two adults on 19 and 20 December: the train or "
                     "road there and back, one night's stay and the places to visit. Stop when you have chosen "
                     "where to book the travel or the stay."),
              arms=["ty", "baseline"]),
]


class ArmResult(BaseModel):
    sessions: int = 0
    finished: int = 0  # sessions that reached booking_chosen
    median_s_to_plan: float | None = None
    median_s_to_booking: float | None = None


class TaskReport(BaseModel):
    task: str
    title: str | None
    baseline: ArmResult
    ty: ArmResult
    reduction_pct: float | None  # 100 * (baseline - ty) / baseline, on median time to booking
    met: bool | None  # None until both arms have MIN_SESSIONS finished sessions


class StudyReport(BaseModel):
    target_pct: float = TARGET_PCT
    min_sessions: int = MIN_SESSIONS
    tasks: list[TaskReport]
    overall: TaskReport  # all tasks pooled; its verdict waits until every task has MIN_SESSIONS per arm


def _reduction(base: float | None, ty: float | None) -> float | None:
    if not base or ty is None:
        return None
    return round(100 * (base - ty) / base, 1)


def _verdict(b: ArmResult, t: ArmResult, pct: float | None) -> bool | None:
    if pct is None or min(b.finished, t.finished) < MIN_SESSIONS:
        return None
    return pct >= TARGET_PCT


def _arm(events: list[MetricEvent], task: str | None, arm: Arm) -> ArmResult:
    """One arm of one task, or of every task pooled when task is None."""
    rows = [e for e in events if e.arm == arm and (task is None or e.task == task)]
    plan, book = _times(rows, "plan_shown"), _times(rows, "booking_chosen")
    return ArmResult(sessions=len({(e.task, e.session_id) for e in rows if e.event == "start"}), finished=len(book),
                     median_s_to_plan=statistics.median(plan) if plan else None,
                     median_s_to_booking=statistics.median(book) if book else None)


def _times(rows: list[MetricEvent], event: str) -> list[float]:
    """Seconds from each session's first start to its first `event` (same rule as summarise)."""
    first: dict[tuple[str, str], dict[str, MetricEvent]] = {}
    for e in rows:
        seen = first.setdefault((e.task, e.session_id), {})
        if e.event not in seen or e.at < seen[e.event].at:
            seen[e.event] = e
    out = []
    for seen in first.values():
        if "start" in seen and event in seen and seen[event].at >= seen["start"].at:
            out.append((seen[event].at - seen["start"].at).total_seconds())
    return out


def _report(events: list[MetricEvent], task: str | None, title: str | None) -> TaskReport:
    b, t = _arm(events, task, "baseline"), _arm(events, task, "ty")
    pct = _reduction(b.median_s_to_booking, t.median_s_to_booking)
    return TaskReport(task=task or "all", title=title, baseline=b, ty=t, reduction_pct=pct, met=_verdict(b, t, pct))


def report(events: list[MetricEvent]) -> StudyReport:
    titles = {t.id: t.title for t in TASKS}
    ids = list(titles) + sorted({e.task for e in events} - set(titles))
    tasks = [_report(events, i, titles.get(i)) for i in ids]
    overall = _report([e for e in events if e.task in titles], None, "All study tasks")
    if any(t.met is None for t in tasks if t.task in titles):  # a pooled median must not hide a thin task
        overall = overall.model_copy(update={"met": None})
    return StudyReport(tasks=tasks, overall=overall)

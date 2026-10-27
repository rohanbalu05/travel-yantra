"""Shortest paths over the transport graph: Dijkstra (baseline) and A*.

Objective per leg: alpha*minutes + beta*cost_inr + gamma*transfer, where a
transfer is a change of (mode, ref) between consecutive legs. Search state is
(node, last leg key) so the transfer term is exact. Stdlib plus ty_contracts."""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta

from ty_contracts import Leg, Mode, TransportOption

from .graph import Edge, Graph, haversine_km

START = datetime(2026, 1, 1, 8, 0)  # ponytail: no timetable waits yet, legs are chained back to back


@dataclass(frozen=True)
class Weights:
    alpha: float = 1.0  # per minute
    beta: float = 0.0  # per INR
    gamma: float = 0.0  # per transfer


@dataclass(frozen=True)
class SearchResult:
    option: TransportOption
    objective: float
    expansions: int
    edges: tuple[Edge, ...]


def _key(e: Edge) -> tuple[str, str]:
    return (e.mode, e.ref)


def _max_speed_km_per_min(g: Graph) -> float:
    """Fastest straight-line pace any edge achieves; keeps the time heuristic admissible."""
    best = 0.0
    for e in g.edges():
        if e.minutes > 0:
            a, b = g.nodes[e.src], g.nodes[e.dst]
            best = max(best, haversine_km(a.lat, a.lon, b.lat, b.lon) / e.minutes)
    return best


def _search(g: Graph, src: str, dst: str, w: Weights, use_heuristic: bool) -> SearchResult | None:
    if src == dst or src not in g.nodes or dst not in g.nodes:  # same node: no legs, no option
        return None
    goal = g.nodes[dst]
    vmax = _max_speed_km_per_min(g) if use_heuristic and w.alpha > 0 else 0.0

    def h(node_id: str) -> float:
        # cost and transfer terms have a zero lower bound (walk edges are free), so time only
        if vmax <= 0:
            return 0.0
        n = g.nodes[node_id]
        return w.alpha * haversine_km(n.lat, n.lon, goal.lat, goal.lon) / vmax

    start = (src, None)
    dist = {start: 0.0}
    prev: dict = {}
    tie = itertools.count()
    heap = [(h(src), next(tie), 0.0, start)]
    done: set = set()
    expansions = 0
    while heap:
        _, _, d, state = heapq.heappop(heap)
        if state in done:
            continue
        done.add(state)
        expansions += 1
        node, last = state
        if node == dst:
            path = []
            while state in prev:
                state, e = prev[state]
                path.append(e)
            return _result(tuple(reversed(path)), d, expansions)
        for e in g.neighbors(node):
            step = w.alpha * e.minutes + w.beta * e.cost_inr
            if last is not None and last != _key(e):
                step += w.gamma
            nxt = (e.dst, _key(e))
            nd = d + step
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                prev[nxt] = (state, e)
                heapq.heappush(heap, (nd + h(e.dst), next(tie), nd, nxt))
    return None


def _result(edges: tuple[Edge, ...], objective: float, expansions: int) -> SearchResult:
    t, legs = START, []
    for e in edges:
        mins = round(e.minutes)
        mode = Mode.road if e.mode == "walk" else Mode(e.mode)  # contract has no walk mode
        legs.append(Leg.model_validate(dict(
            {"from": e.src}, to=e.dst, mode=mode, depart=t,
            arrive=t + timedelta(minutes=mins), minutes=mins, cost_inr=round(e.cost_inr))))
        t += timedelta(minutes=mins)
    by_mode: dict[Mode, int] = {}
    for leg in legs:
        by_mode[leg.mode] = by_mode.get(leg.mode, 0) + leg.minutes
    weight = sum(e.minutes for e in edges) or 1e-9
    comfort = sum(e.comfort * e.minutes for e in edges) / weight
    opt = TransportOption(mode=max(by_mode, key=by_mode.get), legs=legs,
                          total_minutes=sum(leg.minutes for leg in legs),
                          total_cost_inr=sum(leg.cost_inr for leg in legs),
                          comfort=min(5, max(1, round(comfort * 5))))
    return SearchResult(opt, objective, expansions, edges)


def dijkstra(g: Graph, src: str, dst: str, w: Weights | None = None) -> SearchResult | None:
    return _search(g, src, dst, w or Weights(), use_heuristic=False)


def astar(g: Graph, src: str, dst: str, w: Weights | None = None) -> SearchResult | None:
    return _search(g, src, dst, w or Weights(), use_heuristic=True)

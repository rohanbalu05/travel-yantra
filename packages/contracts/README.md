# packages/contracts (TY1 core)

Shared Pydantic models (`ty_contracts`) and generated TypeScript types. Additive changes by TY1 at any time; breaking changes need HQ approval.

- Install: `pip install -e packages/contracts`, then `from ty_contracts import Itinerary, PlanEvent`.
- Regenerate `schema.json` and `ts/index.ts` after any model change: `python packages/contracts/scripts/gen_ts.py`.
- Regenerate samples: `python packages/contracts/scripts/build_samples.py`.
- Test: `pytest packages/contracts` (fails if generated files are stale).

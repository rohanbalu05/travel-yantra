# Katha taste gate

The check in `design/katha-style.md` ("The taste gate") before Katha scales:
does the pipeline write stories people prefer to what a plain prompt gets
from the same model?

## What is here

- `blind/pair-NN/A.md` and `B.md`: one subject and length per pair. One is
  the Katha pipeline's story, the other is the same model given only
  "Write a N-minute story about X." The order is shuffled per pair, and
  the pairs are not in subject order.
- `ratings.csv`: one row per version. Score 1 to 5 on hook, theme,
  specifics, peak, ending and honesty (the rubric in the style guide), and
  put the preferred version (A or B) on each pair's A row.
- `key/`: the answers. `key/key.json` says which of A and B is the Katha;
  `key/<subject>-<len>min/` holds the Katha as served (`katha.json`), the
  plain version, and `notes.json` (the outline, the self-critiques and the
  facts it drew on). Open it only after rating.
- `calls.log`: every live model call that built the pack.

## Subjects

Vittala Temple (Hampi; a temple), Mysuru (a city) and Devaraja Market
(Mysuru; a market and its food), each at 2, 5 and 10 minutes.

## How to rate

1. Read A and B of a pair, in either order, without opening `key/`.
2. Fill both rows of the pair in `ratings.csv`.
3. Pass: the Katha averages 4 or more, and wins most pairs.

The two versions are not indistinguishable. The Katha carries Legend and
History labels and numbered sources, and the plain one does not, because
honesty is one of the scores. Rate the writing, not the formatting.

## Rebuilding

From `apps/api`, with a seeded `DATABASE_URL` and Vertex configured:

    TY_FAKE_LLM=0 uv run python -m guide.scripts.katha_taste_gate

Pairs that already exist are kept. Delete a `key/<subject>-<len>min/` folder
to rewrite that pair.

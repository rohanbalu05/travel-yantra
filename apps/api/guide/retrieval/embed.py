"""Embeddings for the Katha corpus, behind one small interface.

Production uses the local multilingual-e5-small model (free, no API key). It is
trained with prefixes: a document is "passage: ..." and a query is "query: ...".
Get it wrong and nothing breaks loudly, retrieval just gets worse, so the
prefixes live here and are applied in one place.

Tests (and any machine without torch) set EMBEDDER=fake: a deterministic hashed
bag-of-words vector. It makes no network call and needs no model download.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384
BATCH = 32
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "


@lru_cache(maxsize=1)
def model() -> Any:
    """The sentence-transformers model, loaded once, on first use."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def _fake(text: str) -> np.ndarray:
    vec = np.zeros(DIM, dtype=np.float32)
    for word in re.findall(r"\w+", text.lower()):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


def _encode(texts: Sequence[str], prefix: str) -> np.ndarray:
    if os.environ.get("EMBEDDER") == "fake":
        return np.stack([_fake(t) for t in texts]) if texts else np.zeros((0, DIM), np.float32)
    vectors = model().encode(
        [prefix + t for t in texts],
        batch_size=BATCH,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_passages(texts: Sequence[str]) -> np.ndarray:
    """(n, 384) unit vectors for corpus text."""
    return _encode(list(texts), PASSAGE_PREFIX)


def embed_query(text: str) -> np.ndarray:
    """A single (384,) unit vector for a search query."""
    return _encode([text], QUERY_PREFIX)[0]


#: Kannada names for the hub cities. A Kannada query has to find an English
#: paragraph, and e5-small only manages that reliably when the passage carries
#: the place name in both scripts.
CITY_KN = {
    "Mysuru": "ಮೈಸೂರು",
    "Hampi": "ಹಂಪಿ",
    "Bengaluru": "ಬೆಂಗಳೂರು",
    "Chikmagalur": "ಚಿಕ್ಕಮಗಳೂರು",
    "Coorg": "ಕೊಡಗು",
    "Goa": "ಗೋವಾ",
}


def chunk_text(title: str | None, body: str, aliases: Sequence[str] = ()) -> str:
    """What actually gets embedded: title, body, and the names of place and city."""
    text = f"{title}. {body}" if title else body
    named = " ".join(dict.fromkeys(a for a in aliases if a))
    return f"{text} {named}".strip() if named else text

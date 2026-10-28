"""Retrieval. Pure tests run anywhere; DB tests need DATABASE_URL (pgvector)."""

import numpy as np
import pytest

from guide.retrieval import embed
from guide.retrieval.retrieve import Filters, TripContext, fuse, rank, search


class Recorder:
    """Stands in for the sentence-transformers model and keeps what it was given."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def encode(self, texts, **kwargs):
        self.seen.extend(texts)
        return np.ones((len(texts), embed.DIM), dtype=np.float32)


def test_e5_prefixes_are_actually_applied(monkeypatch) -> None:
    monkeypatch.delenv("EMBEDDER")
    recorder = Recorder()
    monkeypatch.setattr(embed, "model", lambda: recorder)
    embed.embed_passages(["Mysore Palace burned in 1897."])
    embed.embed_query("when did the palace burn")
    assert recorder.seen[0].startswith("passage: ")
    assert recorder.seen[1].startswith("query: ")


def test_fake_embedder_is_deterministic_and_normalised() -> None:
    a, b = embed.embed_query("Hampi was sacked"), embed.embed_query("Hampi was sacked")
    assert a.shape == (384,) and np.array_equal(a, b)
    assert float(np.linalg.norm(a)) == pytest.approx(1.0, abs=1e-4)


def test_chunk_text_carries_the_title_and_the_names() -> None:
    text = embed.chunk_text("The oil", "The stone is black.", ("Nandi Statue", "ನಂದಿ"))
    assert text.startswith("The oil. The stone is black.")
    assert "Nandi Statue" in text and "ನಂದಿ" in text
    assert embed.chunk_text("T", "B", ("x", "", "x")) == "T. B x"


def test_rrf_puts_a_doc_both_retrievers_found_above_a_single_retriever_doc() -> None:
    found = {
        "dense": [{"id": 2, "strict": True}, {"id": 1, "strict": True}],
        "lexical": [{"id": 3, "strict": True}, {"id": 1, "strict": True}],
    }
    scores, ranks = fuse(found)
    assert scores[1] > scores[2] and scores[1] > scores[3]
    assert sorted(ranks[1]) == ["dense", "lexical"]


def test_the_loose_lexical_fallback_does_not_get_a_vote() -> None:
    found = {
        "dense": [{"id": 1}, {"id": 2}],
        "lexical": [{"id": 9, "strict": False}, {"id": 8, "strict": False}],
    }
    assert set(rank(found)[0]) == {1, 2}
    found["lexical"] = [{"id": 9, "strict": True}]
    assert 9 in rank(found)[0]


def test_seed_loads_the_expected_counts(db) -> None:
    n = lambda q: db.execute(q).fetchone()[0]
    assert n("SELECT count(*) FROM poi") >= 112
    assert n("SELECT count(*) FROM doc_chunk WHERE NOT retired") >= 288
    assert n("SELECT count(*) FROM doc_chunk WHERE NOT retired AND is_legend") >= 22
    assert n("SELECT count(*) FROM doc_chunk WHERE NOT retired AND embedding IS NULL") == 0


# The DB tests run on the fake embedder, a hashed bag of words whose cosine is
# noise on this corpus. So they lean on names the lexical side can match, and
# paraphrase recall stays a live-smoke check against the real model.


def test_a_named_question_finds_its_chunk(db) -> None:
    hits = search("the battle of Talikota", db, k=8)
    assert "Six months of burning" in {h.title for h in hits}
    for hit in hits:
        assert hit.retrievers and set(hit.retrievers) <= {"dense", "lexical"}
        assert (hit.dense_rank is not None) == ("dense" in hit.retrievers)


def test_the_refusal_path_triggers_on_nonsense(db) -> None:
    assert search("asdkjfh qwerty zxcvbnm blorp", db) == []
    assert search("who invented Mysore pak", db)


def test_filters_actually_filter(db) -> None:
    hampi = search("temple", db, filters=Filters(city="Hampi"), k=8)
    assert hampi and all(h.city == "Hampi" for h in hampi)
    stories = search("temple", db, filters=Filters(city="Hampi", chunk_type="story"), k=8)
    assert stories and all(h.chunk_type == "story" for h in stories)
    again = search("temple", db, filters=Filters(city="Hampi", exclude_ids=[hampi[0].id]))
    assert hampi[0].id not in {h.id for h in again}


def test_trip_context_lifts_the_stop_you_are_standing_at(db) -> None:
    (poi_id,) = db.execute(
        "SELECT id FROM poi WHERE name = 'Chamundeshwari Temple'"
    ).fetchone()
    plain = search("climb", db, k=5)
    assert plain and plain[0].poi_id != poi_id
    aware = search(
        "climb",
        db,
        k=5,
        trip_context=TripContext(current_poi=poi_id, has_elderly=True),
    )
    assert aware and aware[0].poi_id == poi_id


def test_concurrent_first_calls_load_the_embedder_once(monkeypatch):
    import threading
    import time

    loads = []

    def slow_load():
        loads.append(1)
        time.sleep(0.2)  # the real e5 load takes 10-60 s on one throttled vCPU
        return object()

    monkeypatch.setattr(embed, "_model", None)
    monkeypatch.setattr(embed, "_load", slow_load)
    got = []
    threads = [threading.Thread(target=lambda: got.append(embed.model())) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(loads) == 1 and len({id(m) for m in got}) == 1 and len(got) == 4


def test_hindi_and_kannada_questions_get_their_own_similarity_bar() -> None:
    from guide.retrieval.retrieve import (
        MIN_SIMILARITY,
        MIN_SIMILARITY_INDIC,
        min_similarity_for,
    )

    assert min_similarity_for("What should I know before a houseboat trip?") == MIN_SIMILARITY
    assert min_similarity_for("हाउसबोट यात्रा से पहले क्या जानना चाहिए?") == MIN_SIMILARITY_INDIC
    assert min_similarity_for("ಮೈಸೂರು ಅರಮನೆ ಯಾರು ಕಟ್ಟಿಸಿದರು?") == MIN_SIMILARITY_INDIC
    assert min_similarity_for("Taj Mahal का इतिहास") == MIN_SIMILARITY  # mostly Latin letters

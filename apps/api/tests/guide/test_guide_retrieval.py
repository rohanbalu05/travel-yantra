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


def test_a_named_question_finds_its_chunk(db) -> None:
    hits = search("what happened at the battle of Talikota", db, k=8)
    assert hits
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
    aware = search(
        "what should I know before I go",
        db,
        k=5,
        trip_context=TripContext(current_poi=poi_id, has_elderly=True),
    )
    assert aware and aware[0].poi_id == poi_id

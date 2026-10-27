import datetime as dt

import pytest

from routes.compare import UnknownPlace
from routes.stays import rank_stays

IN, OUT = dt.date(2026, 12, 11), dt.date(2026, 12, 14)


def test_goa_family_stays_ranked_by_rating_within_budget():
    stays = rank_stays("Goa", IN, OUT, party=4, budget_per_night_inr=12000)
    assert [s.name for s in stays] == ["Sample Fontainhas Heritage Stay", "Sample Mandovi Riverside Inn",
                                       "Sample Altinho Budget Rooms"]
    assert all(s.city == "Panaji" and s.check_in == IN and s.check_out == OUT for s in stays)
    # 4 people in rooms that sleep 3: two rooms
    assert stays[0].price_per_night_inr == 2 * 5600


def test_over_budget_stays_come_last_cheapest_first():
    stays = rank_stays("Panaji", IN, OUT, party=2, budget_per_night_inr=2000, limit=4)
    assert stays[0].name == "Sample Altinho Budget Rooms"
    assert [s.price_per_night_inr for s in stays[1:]] == [4200, 5600, 7800]


def test_no_budget_ranks_by_rating_and_limit():
    stays = rank_stays("Mysore", IN, OUT, party=2, limit=2)
    assert [s.name for s in stays] == ["Sample Chamundi Hills Retreat", "Sample Palace View Residency"]


@pytest.mark.parametrize("args,exc", [
    (("Atlantis", IN, OUT), UnknownPlace),
    (("Chennai", IN, OUT), UnknownPlace),
    (("Goa", OUT, IN), ValueError),
    (("Goa", IN, IN), ValueError),
])
def test_bad_input(args, exc):
    with pytest.raises(exc):
        rank_stays(*args)


def test_bad_party():
    with pytest.raises(ValueError):
        rank_stays("Goa", IN, OUT, party=0)

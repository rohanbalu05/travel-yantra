import json

from app import qa

HI = "यह एक सुंदर जगह है"


class Back:
    """Fake back-translator: looks the output up in a table, else returns it unchanged."""

    def __init__(self, table):
        self.table = table

    def translate_to_en(self, texts, source):
        return [self.table.get(t, t) for t in texts]


class Judge:
    def __init__(self, scores):
        self.scores, self.calls = scores, 0

    def score(self, src, out, lang):
        self.calls += 1
        return self.scores.get(out, 5)


def test_chrf_identical_and_different():
    assert qa.chrf("a nice place", "a nice place") == 1.0
    assert qa.chrf("a nice place", "zzzz") == 0.0


def test_short_string_and_entity_edge_cases():
    assert qa.chrf("Go", "Go") == 1.0
    r = qa.run_qa([("Go", "जाओ")], "hi", Back({"जाओ": "Go"}), Judge({}))[0]
    assert not r.fell_back
    # unmapped place keeps its Latin spelling without failing the script check
    r = qa.run_qa(
        [("Visit Mysuru Palace", "Mysuru Palace जाएँ")],
        "hi",
        Back({"Mysuru Palace जाएँ": "Visit Mysuru Palace"}),
        Judge({}),
        entities=["Mysuru Palace"],
    )[0]
    assert not r.fell_back
    # "Goa" must not match inside "Goan"
    pairs = [("Try Goan food", "गोअन भोजन आज़माएँ"), ("Visit Goa", "गोवा जाएँ")]
    back = Back({"गोअन भोजन आज़माएँ": "Try Goan food", "गोवा जाएँ": "Visit Goa"})
    res = qa.run_qa(pairs, "hi", back, Judge({}), entities=["Goa"], names={"Goa": {"hi": "गोवा"}})
    assert not any(r.fell_back for r in res)


def test_good_output_passes_and_bad_ones_fall_back():
    pairs = [
        ("This is a beautiful place", HI),  # good
        ("Visit Hampi today", "aaj dekhen"),  # Latin script
        ("Book a train to Goa", "ट्रेन बुक करें"),  # back-translation drifts, judge says 2
    ]
    back = Back({HI: "This is a beautiful place", "ट्रेन बुक करें": "Eat the cake now"})
    judge = Judge({"ट्रेन बुक करें": 2})
    res = qa.run_qa(pairs, "hi", back, judge, entities=["Hampi"])
    assert res[0].flags == [] and res[0].out == HI
    assert {"wrong_script", "entity_lost:Hampi", "fallback_en"} <= set(res[1].flags)
    assert res[1].out == pairs[1][0] and res[1].fell_back
    assert {"low_backtranslation", "low_adequacy"} <= set(res[2].flags)


def test_thresholds_are_configurable():
    pairs = [("This is a beautiful place", HI)]
    back = Back({HI: "This is a beautiful place"})
    strict = qa.Thresholds(min_adequacy=5)
    assert qa.run_qa(pairs, "hi", back, Judge({HI: 4}), th=strict)[0].fell_back
    assert not qa.run_qa(pairs, "hi", back, Judge({HI: 4}))[0].fell_back


def test_judge_not_called_twice_for_same_pair():
    j = Judge({})
    wrapped = qa.Judged(j)
    wrapped.score("a", "b", "hi")
    wrapped.score("a", "b", "hi")
    assert j.calls == 1


def test_report_json_and_markdown():
    back = Back({HI: "This is a beautiful place"})
    res = qa.run_qa(
        [("This is a beautiful place", HI), ("Visit Hampi", "Visit")], "hi", back, Judge({})
    )
    data = json.loads(qa.report_json(res))
    assert data["hi"]["n"] == 2 and data["hi"]["pass_rate"] == 0.5
    assert "fallback_en" in data["hi"]["flags"]
    md = qa.report_markdown(res)
    assert md.startswith("| Language |") and "| hi | 2 | 50% |" in md

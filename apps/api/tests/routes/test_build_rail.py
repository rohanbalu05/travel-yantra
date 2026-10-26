import json
from pathlib import Path

from routes.scripts.build_rail import build

RAW = Path(__file__).resolve().parents[2] / "routes" / "data" / "sample_raw"


def test_build_filters_states(tmp_path):
    counts = build(RAW, tmp_path)
    stations = json.loads((tmp_path / "rail_stations.json").read_text())
    codes = {s["code"] for s in stations}
    assert "DEL" not in codes and {"SBC", "MAO"} <= codes
    assert counts == {"stations": 13, "trains": 7}

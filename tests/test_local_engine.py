"""The Kaaval app runs its review engine locally, end to end, with no outside service and no keys."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import engine

REF = """v {xschem version=3.4.5 file_version=1.2}
"""


def test_local_engine_runs_on_its_own():
    assert engine.configured() and not hasattr(engine, "fix")         # no outside sizing service any more
    h = engine.health()
    assert h["ok"] and h["ngspice"].startswith("ngspice-") and h["pdk"] == "sky130", h
    ws = engine.upload({"a/amp.spice": ".subckt amp vdd vss out\nR1 vdd out 10k\nXM1 out out vss vss sky130_fd_pr__nfet_01v8 L=1 W=2\n.ends amp\n"})
    cells = engine.cells(ws)
    assert [c["cell"] for c in cells] == ["a/amp.spice#amp"]
    r = engine.plan(ws, {"cell": "a/amp.spice#amp", "kind": "powerup", "supplies": {"vdd": 1.8}, "grounds": ["vss"],
                         "corners": ["tt"], "temps": [27], "vscales": [1.0]})
    assert r["ok"] and r["findings"] == [] and r["results"][0]["i_op"] > 1e-6, r


def test_sizing_fix_needs_muse():
    from app import planner, sizing
    key = os.environ.pop("MUSE_API_KEY", None)
    try:
        sizing.fix({"a.sch": "v {}"}, "a.sch", {"device": "m1"})
    except planner.PlannerError as e:
        assert "not connected" in str(e)
    else:
        raise AssertionError("a sizing fix ran without Muse Spark")
    finally:
        if key:
            os.environ["MUSE_API_KEY"] = key


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

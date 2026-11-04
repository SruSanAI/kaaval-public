"""PVT findings carry every condition where they fail, so the bench grid marks exactly those cells whatever the rule
(3 Nov: a bias-collapse finding ringed its worst cell, which the grid showed green: it coloured headroom only)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks  # noqa: E402


def test_headroom_and_bias_list_their_failing_conditions():
    nom = ("tt", 27, 1.0)
    op = lambda region, vds, i: {"m1": dict(region=region, vds=vds, vdsat=0.2, id=i)}
    sweep = {nom: (op("sat", 0.5, 1e-4), None), ("ss", -40, 0.9): (op("triode", 0.1, 1e-4), None),
             ("fs", -40, 0.9): (op("sat", 0.5, 5e-6), None), ("ff", 125, 1.1): (op("sat", 0.5, 1e-4), None)}
    h, = checks.headroom(sweep)
    assert h["conds"] == [["ss", -40, 0.9]] and h["n_bad"] == 1, h
    b, = checks.bias(sweep)
    assert b["conds"] == [["fs", -40, 0.9]] and b["worst"] == ("fs", -40, 0.9), b


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

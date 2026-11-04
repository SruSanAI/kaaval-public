"""kaaval_engine.layout3d: a .mag read as stacked layers, sub-cells placed by their transforms (and arrays), unknown
layers left out, and paths outside the repository refused. No tools needed."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import layout3d as L  # noqa: E402

TOP = """magic
tech sky130A
magscale 1 2
<< metal1 >>
rect 0 0 100 20
<< labels >>
rect 0 0 1 1
<< mystery >>
rect 0 0 5 5
use leaf leaf_0
timestamp 1
transform 1 0 200 0 1 50
box 0 0 10 10
use leaf leaf_1
array 0 2 30 0 0 0
timestamp 1
transform -1 0 0 0 1 0
box 0 0 10 10
<< end >>
"""
LEAF = """magic
tech sky130A
<< poly >>
rect 0 0 10 4
<< end >>
"""


def test_flatten_and_stack():
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "mag"))
    open(os.path.join(d, "mag", "top.mag"), "w").write(TOP)
    open(os.path.join(d, "mag", "leaf.mag"), "w").write(LEAF)
    r = L.read(d, "mag/top.mag")
    by = {l["name"]: l for l in r["layers"]}
    assert set(by) == {"metal1", "poly"} and r["cells"] == ["leaf", "top"], (by.keys(), r["cells"])
    assert by["metal1"]["rects"] == [(0, 0, 100, 20)] and by["metal1"]["z"] > by["poly"]["z"]
    assert (200, 50, 210, 54) in by["poly"]["rects"]                       # translated
    assert (-10, 0, 0, 4) in by["poly"]["rects"] and (-70, 0, -60, 4) in by["poly"]["rects"]   # mirrored, arrayed x3
    assert len(by["poly"]["rects"]) == 4 and r["unit_um"] == 0.005 and r["bbox"] == [-70, 0, 210, 54]
    try:
        L.read(d, "../etc/passwd.mag")
    except ValueError:
        pass
    else:
        raise AssertionError("a path outside the repository was read")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

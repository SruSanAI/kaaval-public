"""examples/demo_tapeout is the reference of test_kaaval_startup.py (BETA), drawn as xschem schematics: the files on
disk match what tools/make_demo_tapeout.py writes, Kaaval netlists them to BETA's devices, and the tile reads as one
analog block on ua[0]. No simulation."""
import os, re, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools"))
from kaaval_engine import chip, sim  # noqa: E402
import make_demo_tapeout as M  # noqa: E402
from test_kaaval_startup import BETA  # noqa: E402

D = os.path.join(HERE, "examples", "demo_tapeout")


def _devices(text, ground):
    out = set()
    for line in text.splitlines():
        t = line.split()
        if t and t[0][0] in "XR" and not t[0].lower().startswith("x1"):
            k = 5 if t[0][0] == "X" else 3                   # a transistor has 4 nets, a resistor 2
            rest = re.sub(r" (m|mult)=1\b", "", " " + " ".join(t[k:])).split(" ad=")[0].strip()
            out.add((t[0].upper(), tuple(ground.get(n, n) for n in t[1:k]), rest))
    return out


def test_files_are_what_the_generator_writes():
    with tempfile.TemporaryDirectory() as t:
        M.OUT = t
        M.main()
        for d, _, fs in os.walk(t):
            for f in fs:
                rel = os.path.relpath(os.path.join(d, f), t)
                assert open(os.path.join(D, rel)).read() == open(os.path.join(d, f)).read(), rel


def test_netlist_is_the_tested_reference():
    tb = sim.Testbench.from_sch(os.path.join(D, "xschem", "tb_ref.sch"))
    ours = _devices(tb.circuit, {"vss": "0", "GND": "0"})
    beta = _devices(BETA, {})
    assert ours == beta, (ours ^ beta)
    assert "x1 vdd GND iout kv_ref" in tb.circuit and "R2 iout GND 50k" in tb.circuit and tb.analyses == [".op"]


def test_tile_is_one_analog_block_on_ua0():
    t = chip.read(D)
    assert t["top"] == "tt_um_kaaval_demo" and t["analog_pads"] == ["ua[0]"]
    assert [(i["type"], i["cell"], i["analog"]) for i in t["instances"]] == [("kv_ref", "xschem/kv_ref.sch", True)]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

"""examples/demo_mixed is what tools/make_demo_mixed.py writes: a two-rail tile (VDPWR, VAPWR) of four analog blocks,
the oscillator drawn with wires and driven by a transient testbench. No simulation."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from kaaval_engine import chip, sim  # noqa: E402
import make_demo_mixed as M  # noqa: E402

D = os.path.join(HERE, "examples", "demo_mixed")


def test_files_are_what_the_generator_writes():
    with tempfile.TemporaryDirectory() as t:
        M.OUT = t
        M.main()
        for d, _, fs in os.walk(t):
            for f in fs:
                rel = os.path.relpath(os.path.join(d, f), t)
                assert open(os.path.join(D, rel)).read() == open(os.path.join(d, f)).read(), rel


def test_tile_has_two_rails_and_four_blocks():
    t = chip.read(D)
    assert t["top"] == "tt_um_kaaval_mixed" and t["uses_3v3"] and "VAPWR" in t["rails"]
    assert [i["type"] for i in t["instances"]] == ["kv_osc", "kv_xref", "kv_cross", "kv_vref"]


def test_oscillator_is_a_wired_ring_with_a_transient_testbench():
    tb = sim.Testbench.from_sch(os.path.join(D, "xschem", "tb_osc.sch"))
    assert any(a.startswith(".tran") for a in tb.analyses), tb.analyses
    assert sum(1 for l in open(os.path.join(D, "xschem", "kv_osc.sch")) if l.startswith("N ")) >= 30
    nets = {w for l in tb.circuit.splitlines() if l.upper().startswith("XMN") for w in l.split()[1:4]}
    assert {"s1", "s2", "s3", "s4", "osc"} <= nets, nets      # five stages, the last one driving osc back into the first


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

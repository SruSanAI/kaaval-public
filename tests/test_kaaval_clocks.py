"""An on-chip oscillator's clock as SDC (kaaval_engine.clocks), on a cell of our own: a 5-stage sky130 inverter ring.
It must run faster at ff than at tt than at ss, keep a duty cycle near 50 % (a symmetric ring), swing rail to rail,
and give one create_clock per corner with the shortest period of that corner (and the shortest overall in "all").
A cell that does not oscillate is reported, never given a clock. Measured at tt 27 °C: 1.777 ns, 49.7 % duty."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import clocks


def _inv(a, y, i):
    return (f"XP{i} {y} {a} vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1\n"
            f"XN{i} {y} {a} vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=0.5 nf=1 m=1\nC{i} {y} vss 20f")


RING = ".subckt ring5 out vdd vss\n" + "\n".join(_inv(a, y, i) for i, (a, y) in enumerate(
    [("out", "n1"), ("n1", "n2"), ("n2", "n3"), ("n3", "n4"), ("n4", "out")])) + "\n.ends\n"
PORTS = ["out", "vdd", "vss"]


def test_ring_clock_per_corner():
    r = clocks.constraints(RING, "ring5", PORTS, {"vdd": 1.8}, ["vss"], "out", pin="u_osc/out",
                           corners=["tt", "ss", "ff"], temps=[27], vscales=[1.0])
    assert not r["errors"], r["errors"]
    per = {c: r["summary"][c]["period"] for c in ("tt", "ss", "ff")}
    assert per["ff"] < per["tt"] < per["ss"], per
    assert 1.0e-9 < per["tt"] < 3.0e-9, per                                  # 1.777 ns measured
    for _, _, _, m, _ in r["rows"]:
        assert 0.45 < m["duty"] < 0.55 and m["vmax"] - m["vmin"] > 0.9 * 1.8, m
    assert r["summary"]["all"]["period"] == per["ff"]                       # conservative: the fastest anywhere
    for c, text in r["sdc"].items():
        m = re.search(r"^create_clock -name osc_clk -period ([0-9.]+) -waveform \{0 ([0-9.]+)\} "
                      r"\[get_pins \{u_osc/out\}\]$", text, re.M)
        assert m, text
        p, h = float(m.group(1)), float(m.group(2))
        assert abs(p - r["summary"][c]["period"] * 1e9) < 1e-3 and 0.45 * p < h < 0.55 * p
        assert "Jitter is not measured" in text and "set_clock_uncertainty <ns>" in text
    j = clocks.constraints(RING, "ring5", PORTS, {"vdd": 1.8}, ["vss"], "out", corners=["tt"], temps=[27],
                           vscales=[1.0], jitter=20e-12)
    assert "set_clock_uncertainty 0.02 [get_clocks {osc_clk}]" in j["sdc"]["tt"]


RING4 = ".subckt ring4 out vdd vss\n" + "\n".join(_inv(a, y, i) for i, (a, y) in enumerate(
    [("out", "n1"), ("n1", "n2"), ("n2", "n3"), ("n3", "out")])) + "\n.ends\n"


def test_a_cell_that_does_not_oscillate_gets_no_clock():
    r, e = clocks.measure(RING4, "ring4", PORTS, {"vdd": 1.8}, ["vss"], "out", tmax=10e-9)   # even ring: latches
    assert r is None and "does not oscillate" in e, (r, e)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

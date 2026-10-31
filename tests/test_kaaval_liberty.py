"""An analog cell's timing model for static timing analysis (kaaval_engine.liberty), on a cell of our own: a 1.8 V CMOS
inverter characterised in ngspice. Its delays must be positive and grow with load and input slew, its sense must be
negative unate, its input capacitance must be that of its two gates (fF), and the Liberty text must be well formed."""
import os, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import liberty

INV = """.subckt ainv a y vdd vss
XP y a vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=2 nf=1 m=1
XN y a vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
.ends
"""


def test_inverter_timing_model():
    lib = liberty.characterise(INV, "ainv", ["a", "y", "vdd", "vss"], {"vdd": 1.8}, ["vss"], [("a", "y")])
    assert not lib["errors"], lib["errors"]
    g = lib["tables"]["a->y"]
    s0, s1 = liberty.SLEWS
    c0, c1 = liberty.LOADS
    for k in ("d1", "d2", "r1", "f1"):
        assert all(r[k] and r[k] > 0 for r in g.values()), k
        assert g[f"{s0}|{c1}"][k] > g[f"{s0}|{c0}"][k], k            # more load, slower
    assert g[f"{s1}|{c0}"]["d1"] > g[f"{s0}|{c0}"]["d1"]             # slower input, later output
    assert all(r["sense"] == "negative_unate" for r in g.values())
    t = lib["text"]
    assert t.count("{") == t.count("}") and "timing_sense : negative_unate;" in t and 'related_pin : "a";' in t
    cap = float(re.search(r"pin \(a\) \{\s*direction : input;\s*capacitance : ([0-9.]+);", t).group(1))
    assert 0.001 < cap < 0.02, cap                                   # pF: a few fF of gate
    if shutil.which("yosys"):                                        # a real Liberty reader accepts it
        with tempfile.TemporaryDirectory() as d:
            open(f"{d}/a.lib", "w").write(t)
            r = subprocess.run(["yosys", "-q", "-p", f"read_liberty -lib {d}/a.lib"], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr


# a StrongARM latch of our own: clock low resets both sides high; clock high, the side with the higher input pulls its
# output node down first and the cross-coupled pair latches. out = NOT outn rises when inp is above inn; a dummy
# inverter on outp keeps the two sides equally loaded (otherwise the load alone is an input offset).
SA = """.subckt sarm clk inp inn out vdd vss
XT tail clk vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=4 nf=1 m=1
X1 x1 inp tail vss sky130_fd_pr__nfet_01v8 L=0.15 W=4 nf=1 m=1
X2 x2 inn tail vss sky130_fd_pr__nfet_01v8 L=0.15 W=4 nf=1 m=1
X3 outn outp x1 vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
X4 outp outn x2 vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
X5 outn outp vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1
X6 outp outn vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1
X7 outn clk vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1
X8 outp clk vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1
X9 x1 clk vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=0.5 nf=1 m=1
X10 x2 clk vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=0.5 nf=1 m=1
XP out outn vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=2 nf=1 m=1
XN out outn vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
XPD outd outp vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=2 nf=1 m=1
XND outd outp vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
.ends
"""
SA_PORTS = ["clk", "inp", "inn", "out", "vdd", "vss"]


def test_comparator_decides_slower_as_the_input_difference_shrinks():
    """Clock -> output of a clocked comparator: the latch takes longer the smaller the input difference, so a timing
    model must name the overdrive it was measured at. Measured on this latch at tt: 100 / 146 / 193 / 222 ps at
    100 mV / 10 mV / 1 mV / 0.1 mV, about 46 ps per decade down to 1 mV (the regeneration time constant), flattening
    below 0.1 mV in a noiseless simulation (clock kick-back sets the starting imbalance there)."""
    rows = liberty.decision_times(SA, "sarm", SA_PORTS, {"vdd": 1.8}, ["vss"], "clk", "out", "inp", "inn", 0.9,
                                  overdrives=(0.1, 0.01, 0.001))
    assert all(d and not e for _, d, e in rows), rows
    d = [x[1] for x in rows]
    assert d[0] < d[1] < d[2], d
    assert 0.3 < (d[2] - d[1]) / (d[1] - d[0]) < 3, d                 # about equal steps per decade (log law)


def test_comparator_timing_model_is_a_clock_arc():
    lib = liberty.characterise(SA, "sarm", SA_PORTS, {"vdd": 1.8}, ["vss"], [("clk", "out", "rising_edge")],
                               {"inp": 0.9005, "inn": 0.8995}, note="Characterised at a 1 mV overdrive.")
    assert not lib["errors"], lib["errors"]
    t = lib["text"]
    assert "timing_type : rising_edge;" in t and "clock : true;" in t and "1 mV overdrive" in t
    assert "cell_rise" in t and "cell_fall" not in t and t.count("{") == t.count("}")
    if shutil.which("yosys"):
        with tempfile.TemporaryDirectory() as d:
            open(f"{d}/c.lib", "w").write(t)
            r = subprocess.run(["yosys", "-q", "-p", f"read_liberty -lib {d}/c.lib"], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr


def test_comparator_offset_with_mismatch():
    """With sky130 device mismatch (tt_mm, a seed per sample) this latch does not resolve 1 mV: 30 of 40 samples
    decided the wrong way at +-1 mV, 7 of 10 at +-5 mV, none at +-20 mV (input-referred offset of the order of
    10 mV, set by its minimum-length latch). So its timing model must not be written at 1 mV."""
    fine = liberty.offset_check(SA, "sarm", SA_PORTS, {"vdd": 1.8}, ["vss"], "clk", "out", "inp", "inn", 0.9, 0.001,
                                samples=8)
    big = liberty.offset_check(SA, "sarm", SA_PORTS, {"vdd": 1.8}, ["vss"], "clk", "out", "inp", "inn", 0.9, 0.05,
                               samples=8)
    assert fine["errors"] == 0 and big["errors"] == 0, (fine, big)
    assert fine["wrong"] >= 2, fine                     # mismatch makes 1 mV a coin toss
    assert big["wrong"] == 0 and fine["corner"] == "tt_mm", big


def test_offset_gate_refuses_an_overdrive_the_comparator_does_not_resolve():
    """The 1 mV result of test_comparator_offset_with_mismatch (most samples wrong) must not become a .lib; a clean
    result is written and says so; too few samples is written with its bound. The refusal simulates nothing."""
    bad = dict(wrong=27, samples=40, errors=0, rate=27 / 40, rate_hi=0.8, overdrive=0.001, corner="tt_mm")
    good = dict(wrong=0, samples=200, errors=0, rate=0.0, rate_hi=0.019, overdrive=0.02, corner="tt_mm")
    few = dict(wrong=0, samples=10, errors=0, rate=0.0, rate_hi=0.28, overdrive=0.02, corner="tt_mm")
    lib = liberty.characterise(SA, "sarm", SA_PORTS, {"vdd": 1.8}, ["vss"], [("clk", "out", "rising_edge")],
                               offset=bad)
    assert lib["text"] is None and "27 of 40" in lib["errors"][0] and "does not resolve" in lib["errors"][0]
    assert liberty.offset_gate(good) == (True, "0 of 200 mismatch samples (tt_mm) decided the wrong way at +-20 mV.")
    ok, said = liberty.offset_gate(few)
    assert ok and "up to 28 %" in said
    assert liberty.offset_gate(None)[0] and "not checked" in liberty.offset_gate(None)[1]
    assert liberty.offset_gate(bad, clocked=False) == (True, "")     # a plain arc (an inverter) has no offset


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

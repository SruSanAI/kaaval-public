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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

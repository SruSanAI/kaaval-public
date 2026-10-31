"""A testbench that sets its supply with agauss (a Monte Carlo bench): ngspice draws a new value on every run, so
Kaaval fixes each random draw at its nominal value; every corner then simulates the same bench. Our own bench."""
import os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import sim  # noqa: E402

SCH = """v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/vsource.sym} 0 0 0 0 {name=V1 value=VCC}
C {devices/lab_pin.sym} 0 -30 0 0 {name=p1 lab=a}
C {devices/lab_pin.sym} 0 30 0 0 {name=p2 lab=0}
C {devices/res.sym} 100 0 0 0 {name=R1 value=1k}
C {devices/lab_pin.sym} 100 -30 0 0 {name=p3 lab=a}
C {devices/lab_pin.sym} 100 30 0 0 {name=p4 lab=0}
C {devices/code.sym} -200 0 0 0 {name=s1 only_toplevel=false value="
.param VCCG = agauss(1.8, 0.05, 1)
.param VCC = 'VCCG'
.op
"}
"""


def test_nominal_param_forms():
    assert sim.nominal_param(".param V = agauss(1.8, 0.05, 1)") == ".param V = (1.8)"
    assert sim.nominal_param(".param X = gauss(max(1,2), 0.1, 3) + unif(5, 1)") == ".param X = (max(1,2)) + (5)"
    assert sim.nominal_param(".param T = 27") == ".param T = 27"


def test_every_run_simulates_the_same_supply():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "tb.sch"), "w").write(SCH)
    tb = sim.Testbench.from_sch(os.path.join(d, "tb.sch"))
    assert tb.nominal == ["VCCG"] and ".param VCCG = (1.8)" in tb.params, tb.params
    deck = sim.deck(tb, "tt", 27, 1.0)
    assert "agauss" not in deck
    if sim.shutil.which("ngspice"):
        import subprocess
        vals = set()
        for _ in range(2):
            p = os.path.join(d, "d.sp")
            open(p, "w").write(re.sub(r"(?s)\.control.*?\.endc", ".control\nop\nprint v(a)\n.endc", deck))
            out = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=60).stdout
            vals.add(re.search(r"v\(a\) = (\S+)", out).group(1))
        assert len(vals) == 1, vals


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

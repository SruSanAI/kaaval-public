"""Kaaval's loop-stability check (Tian's double injection at a break point), simulated with ngspice.

1. A loop built from controlled sources, broken where both sides load it heavily: the measured loop gain must match
   the exact return ratio of its gain source (unity-gain frequency, phase margin, gain margin).
2. Our own sky130 two-stage Miller op-amp in unity feedback: phase margin must fall as the load grows and rise with a
   bigger compensation capacitor, and the check must flag the thin-margin case and pass the well-compensated one.
3. A break on a pin that is not on the net is refused."""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks, sim

LOOP = """R1 x n1 10k
Rn n1 0 5k
Cn n1 0 2p
G1 out 0 n1 0 2e-3
R2 out 0 20k
C2 out 0 1p
R3 x out 2k
Rx x 0 3k
Cx x 0 5p"""


def opamp(cl, cc):
    return f"""Vdd vdd 0 1.8
Vp inp 0 0.9
Ib vdd vb 20u
XM6 vb vb 0 0 sky130_fd_pr__nfet_01v8 L=1 W=4 nf=1 m=1
XM5 tail vb 0 0 sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
XM1 o1 out tail 0 sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
XM2 o2a inp tail 0 sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
XM3 o1 o1 vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=8 nf=1 m=1
XM4 o2a o1 vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=8 nf=1 m=1
XM7 out o2a vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=32 nf=1 m=1
XM8 out vb 0 0 sky130_fd_pr__nfet_01v8 L=1 W=16 nf=1 m=1
Cc o2a ncz {cc}
Rz ncz out 2k
CL out 0 {cl}"""


def margins(circuit, net, pins):
    circ, _, y = sim.break_net(circuit, net, pins)
    tb = sim.Testbench(sch="own.sch", circuit=circ, analyses=[".op"])
    tb.brk_y = y
    return sim.loopgain_corner(tb, "tt", [(27, 1.0)])[(27, 1.0)]


def test_matches_exact_return_ratio():
    r, e = margins(LOOP, "x", ["R1.1", "Rx.1"])
    assert not e, e
    d = tempfile.mkdtemp()
    open(f"{d}/t.sp", "w").write("* exact\n" + LOOP.replace("G1 out 0 n1 0 2e-3", "It out 0 dc 0 ac 1") +
                                 f"\n.control\nset wr_singlescale\nac dec 20 1 10g\nwrdata {d}/t.txt v(n1)\n.endc\n.end\n")
    subprocess.run(["ngspice", "-b", f"{d}/t.sp"], capture_output=True, cwd=d)
    rows = [list(map(float, l.split())) for l in open(f"{d}/t.txt") if l.strip() and l.split()[0][0].isdigit()]
    exact = sim._margins([a[0] for a in rows], [-2e-3 * complex(a[1], a[2]) for a in rows])
    assert abs(r["pm"] - exact["pm"]) < 0.1 and abs(r["gm_db"] - exact["gm_db"]) < 0.1
    assert abs(r["ugf"] / exact["ugf"] - 1) < 1e-3


def test_opamp_margin_trends_and_findings():
    thin, _ = margins(opamp("10p", "0.5p"), "out", ["XM1.g"])
    mid, _ = margins(opamp("2p", "0.5p"), "out", ["XM1.g"])
    good, _ = margins(opamp("2p", "2p"), "out", ["XM1.g"])
    assert thin["pm"] < mid["pm"] < good["pm"], (thin["pm"], mid["pm"], good["pm"])
    assert thin["pm"] < 30 and good["pm"] > 60
    assert [f["rule"] for f in checks.stability({("tt", 27, 1.0): (thin, None)})] == ["analog/low_phase_margin"]
    assert checks.stability({("tt", 27, 1.0): (good, None)}) == []


def test_break_pin_must_be_on_the_net():
    try:
        sim.break_net(opamp("2p", "2p"), "out", ["XM2.g"])
    except ValueError as e:
        assert "not on net" in str(e)
    else:
        raise AssertionError("a pin that is not on the net was accepted")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

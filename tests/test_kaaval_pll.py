"""A PLL's lock time against the logic's reset (kaaval_engine.clocks.pll_lock / reset_check), on a PLL of our own in
sky130: a two-flip-flop phase-frequency detector (sky130_fd_sc_hd__dfrtp_1, NAND reset with a two-inverter delay:
without it the down flip-flop never clears and the loop sticks at 0.13 V), a transistor charge pump, an RC loop
filter, a 5-stage ring VCO whose pull-downs are starved by the control voltage (116 MHz at 0.9 V to 429 MHz at 1.8 V)
and a divide-by-2. With a 100 MHz reference it locks at 1.030 V with the divided clock at exactly 10.000 ns, 0.2 µs
after the reference starts (measured at tt 27 °C). A reference the VCO cannot reach never locks, and says so."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import clocks

SC = "sky130_fd_sc_hd__"
def stage(a, y, i):
    return (f"XP{i} {y} {a} vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1\n"
            f"XN{i} {y} {a} s{i} vss sky130_fd_pr__nfet_01v8 L=0.15 W=0.5 nf=1 m=1\n"
            f"XS{i} s{i} vctrl vss vss sky130_fd_pr__nfet_01v8 L=0.5 W=1 nf=1 m=1\n"
            f"Cr{i} {y} vss 20f")
RING = "\n".join(stage(a, y, i) for i, (a, y) in enumerate([("r4", "r0"), ("r0", "r1"), ("r1", "r2"), ("r2", "r3"), ("r3", "r4")]))
PLL = f""".subckt pll1 ref out fb vctrl vbp vbn vdd vss
* phase-frequency detector: two flip-flops, reset together by a NAND of their outputs
XU ref vdd rstb vss vss vdd vdd up {SC}dfrtp_1
XD fb vdd rstb vss vss vdd vdd dn {SC}dfrtp_1
XR up dn vss vss vdd vdd rs0 {SC}nand2_1
* reset delay: both flip-flops must clear before the reset lets go (the classic PFD dead zone fix)
XRD1 rs0 vss vss vdd vdd rs1 {SC}inv_1
Crd1 rs1 vss 30f
XRD2 rs1 vss vss vdd vdd rstb {SC}inv_1
Crd2 rstb vss 30f
XI up vss vss vdd vdd upb {SC}inv_1
* charge pump: current sources biased from vbp / vbn, switched by up / dn
XCP1 cp1 vbp vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=8 nf=1 m=1
XCP2 vctrl upb cp1 vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1
XCN2 vctrl dn cn1 vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
XCN1 cn1 vbn vss vss sky130_fd_pr__nfet_01v8 L=1 W=4 nf=1 m=1
* loop filter
R1 vctrl lf 10k
C1 lf vss 4p
C2 vctrl vss 0.4p
* VCO: 5-stage ring, each stage's pull-down starved by vctrl
{RING}
XB r4 vss vss vdd vdd out {SC}inv_1
* divide by 2
XF out fbn vdd vss vss vdd vdd fb {SC}dfrtp_1
XFI fb vss vss vdd vdd fbn {SC}inv_1
.ends
"""
PORTS = ["ref", "out", "fb", "vctrl", "vbp", "vbn", "vdd", "vss"]
BIAS = {"vbp": 0.4, "vbn": 0.9}


ARGS = (PLL, "pll1", PORTS, {"vdd": 1.8}, ["vss"], "ref")


def test_pll_locks_and_the_reset_must_wait():
    r, e = clocks.pll_lock(*ARGS, 100e6, "vctrl", fb="fb", biases=BIAS, tmax=4e-6)
    assert e is None, e
    assert abs(r["fb_period"] - 10e-9) < 0.01e-9 and 0.9 < r["ctrl_final"] < 1.2, r
    assert 0 < r["lock"] < 1.5e-6, r
    assert clocks.reset_check(r["lock"], r["lock"] / 2)               # released too early: a finding
    assert clocks.reset_check(r["lock"], r["lock"] + 1e-6) is None


def test_a_reference_the_vco_cannot_reach_never_locks():
    r, e = clocks.pll_lock(*ARGS, 300e6, "vctrl", fb="fb", biases=BIAS, tmax=3e-6)    # needs 600 MHz, VCO tops at 429
    assert r is None and "not locked" in e, (r, e)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

"""Kaaval's power-up check on circuits of our own, simulated with ngspice and the sky130 models.

A self-biased (beta-multiplier) current reference has two DC solutions, its working bias and zero current. Without a
start-up device a power-up from 0 V stays at zero: the check must say it does not start. The same reference with a
weak always-on start-up device must pass, and so must an inverter biased at its trip point, whose high gain once
looked like a second state."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks, sim

BETA = """V1 vdd 0 1.8
XM1 n1 n1 0 0 sky130_fd_pr__nfet_01v8 L=2 W=4 nf=1 m=1
XM2 n2 n1 s2 0 sky130_fd_pr__nfet_01v8 L=2 W=16 nf=1 m=1
R1 s2 0 20k
XM3 n1 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM4 n2 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM5 iout n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
R2 iout 0 50k"""
STARTUP = "\nXM6 n1 0 vdd vdd sky130_fd_pr__pfet_01v8 L=20 W=0.42 nf=1 m=1"
INVERTER = """V1 vdd 0 1.8
Vin in 0 0.84
XM1 out in 0 0 sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
XM2 out in vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=2 nf=1 m=1"""


def findings(circuit, corners=("tt", "ss")):
    tb = sim.Testbench(sch="own.sch", circuit=circuit, analyses=[".op"])
    sw = {}
    for c in corners:
        for t, r in sim.startup_corner(tb, c, [27], 1.0, ramp=20e-6, settle=300e-6).items():
            sw[(c, t, 1.0)] = r
    return [f["rule"] for f in checks.startup(sw)], sw


def test_reference_without_startup_does_not_start():
    rules, sw = findings(BETA)
    assert rules == ["analog/no_startup"], rules
    assert all(r["i_end"] < 1e-9 and r["i_op"] > 5e-6 for r, e in sw.values())


def test_reference_with_startup_passes():
    rules, sw = findings(BETA + STARTUP)
    assert rules == [], rules
    assert all(abs(r["i_end"] - r["i_op"]) < 0.05 * r["i_op"] for r, e in sw.values())


def test_inverter_at_trip_point_is_not_a_second_state():
    rules, _ = findings(INVERTER, corners=("tt",))
    assert rules == [], rules



def test_step_ladder_agreement_and_marginal_finding():
    """Results agree only within 5 % current and 20 mV per node; a condition no two steps agree on is reported as a
    marginal start-up, not dropped."""
    a = dict(i_end=1e-5, nodes={"x": (1.0, 0.50)})
    assert sim._same(a, dict(i_end=1.02e-5, nodes={"x": (1.0, 0.51)}))
    assert not sim._same(a, dict(i_end=2e-5, nodes={"x": (1.0, 0.50)}))
    assert not sim._same(a, dict(i_end=1e-5, nodes={"x": (1.0, 0.60)}))
    f = checks.startup({("ff", 27, 1.0): (None, "undetermined: the power-up result changes with the simulator's "
                                                 "time step (47.9 µA at 80 ns, 83.3 µA at 2 ns, 81.4 µA at 1 ns)")})
    assert [x["rule"] for x in f] == ["analog/marginal_startup"] and "83.3 µA at 2 ns" in f[0]["message"]


def test_fine_step_budget_reports_unconfirmed_not_marginal():
    """A cell too large for the fine steps (the 2 ns run times out) is "unconfirmed": after the first timeout no other
    condition of the plan tries a fine step, and no finding is made from it."""
    calls = []
    ok = dict(i_op=1e-5, i_end=1e-5, i_prev=1e-5, nodes={"x": (0.5, 0.5)}, confirmed=True)

    def fake(tb, corner, temps, vscale, ramp, settle, timeout, schedule, tmax=None):
        calls.append(tmax)
        return {t: ((dict(ok), None) if tmax is None else (None, "timeout")) for t in temps}

    real, sim.startup_corner = sim.startup_corner, fake
    try:
        fine = sim.budget()
        a = sim.startup_checked(None, "tt", [27, 125], fine=fine)
        b = sim.startup_checked(None, "ss", [27], fine=fine)
    finally:
        sim.startup_corner = real
    assert calls == [None, 2e-9, None], calls
    errs = [e for _, e in list(a.values()) + list(b.values())]
    assert all(e.startswith("unconfirmed") for e in errs), errs
    assert "2 ns at tt run timed out" in errs[2]
    assert checks.startup({("tt", 27, 1.0): (None, errs[0])}) == []

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

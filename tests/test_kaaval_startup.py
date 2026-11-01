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


def test_coarse_disagreement_alone_is_unconfirmed_not_marginal():
    """Default and 2 ns disagree, 1 ns cannot finish: the coarse run is the likely culprit, so the condition is
    unconfirmed. Only 2 ns and 1 ns disagreeing make it marginal."""
    lo = dict(i_op=1e-5, i_end=1e-6, i_prev=1e-6, nodes={"x": (0.5, 0.3)}, confirmed=True)
    hi = dict(lo, i_end=1e-5, nodes={"x": (0.5, 0.5)})
    mid = dict(lo, i_end=5e-6, nodes={"x": (0.5, 0.4)})
    for third, want in (((None, "timeout"), "unconfirmed"), ((dict(mid), None), "undetermined")):
        def fake(tb, corner, temps, vscale, ramp, settle, timeout, schedule, tmax=None):
            return {t: {None: (dict(lo), None), 2e-9: (dict(hi), None), 1e-9: third}[tmax] for t in temps}
        real, sim.startup_corner = sim.startup_corner, fake
        try:
            (r, e), = sim.startup_checked(None, "tt", [27]).values()
        finally:
            sim.startup_corner = real
        assert r is None and e.startswith(want), (want, e)


def test_suspect_conditions_are_confirmed_first_on_their_own_budget():
    """A default-step result that looks like a failure gets its fine-step check before any passing condition, and on
    the suspect budget: passes that use up the shared budget cannot leave a real failure unconfirmed."""
    from kaaval_engine import plan as P
    ok = dict(i_op=1e-5, i_end=1e-5, i_prev=1e-5, nodes={"x": (0.5, 0.5)})
    dead = dict(ok, i_end=1e-10, i_prev=1e-10)
    calls = []

    def fake(tb, corner, temps, vscale, ramp, settle, timeout, schedule, tmax=None):
        calls.append((corner, tmax))
        if tmax is not None and corner != "ss":
            return {t: (None, "timeout") for t in temps}       # passing groups are slow at fine steps
        return {t: (dict(dead if corner == "ss" else ok), None) for t in temps}

    real, sim.startup_corner = sim.startup_corner, fake
    try:
        got = P._checked_sweep(None, [(c, c, 1.0, None) for c in ("tt", "ff", "ss")], [27], 20e-6, 300e-6, 150,
                               lambda key, coarse: any(P._odd(r) for r, e in coarse[key].values()))
    finally:
        sim.startup_corner = real
    assert sorted(c for c, tm in calls if tm is None) == ["ff", "ss", "tt"]          # (default-step runs: in parallel)
    assert [c for c, tm in calls if tm is not None][0] == "ss", calls
    (r, e), = got["ss"].values()
    assert e is None and r["tmax"] == 2e-9, e                    # the failure is confirmed
    assert all(got[c][27][1].startswith("unconfirmed") for c in ("tt", "ff"))


def test_default_step_runs_overlap():
    """The default-step pass runs sim.WORKERS ngspice sessions at once; every group still gets its own result."""
    import threading, time as _t
    from kaaval_engine import plan as P
    ok = dict(i_op=1e-5, i_end=1e-5, i_prev=1e-5, nodes={"x": (0.5, 0.5)})
    live, peak, lock = [0], [0], threading.Lock()

    def fake(tb, corner, temps, vscale, ramp, settle, timeout, schedule, tmax=None):
        if tmax is None:
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            _t.sleep(0.3)
            with lock:
                live[0] -= 1
        return {t: (dict(ok, nodes={"x": (vscale, vscale)}), None) for t in temps}

    real, workers = sim.startup_corner, sim.WORKERS
    sim.startup_corner, sim.WORKERS = fake, 3
    try:
        groups = [(f"{c}{v}", c, v, None) for c in ("tt", "ss", "ff") for v in (0.9, 1.0)]
        t0 = _t.time()
        got = P._checked_sweep(None, groups, [27], 20e-6, 300e-6, 150, lambda key, coarse: False)
        wall = _t.time() - t0
    finally:
        sim.startup_corner, sim.WORKERS = real, workers
    assert peak[0] == 3, peak
    assert wall < 6 * 0.3 * 0.75, wall                          # 6 runs of 0.3 s, 3 at a time
    assert all(got[f"{c}{v}"][27][0]["nodes"]["x"] == (v, v) for c in ("tt", "ss", "ff") for v in (0.9, 1.0))


def test_fine_step_checks_overlap_and_suspects_finish_first():
    """The fine-step checks run sim.WORKERS at once too, and every suspect group is checked before any other group's
    fine step starts; each budget still counts every run's own seconds."""
    import threading, time as _t
    from kaaval_engine import plan as P
    ok = dict(i_op=1e-5, i_end=1e-5, i_prev=1e-5, nodes={"x": (0.5, 0.5)})
    dead = dict(ok, i_end=1e-10, i_prev=1e-10)
    live, peak, lock, events = [0], [0], threading.Lock(), []

    def fake(tb, corner, temps, vscale, ramp, settle, timeout, schedule, tmax=None):
        if tmax is not None:
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
                events.append(("start", corner))
            _t.sleep(0.2)
            with lock:
                live[0] -= 1
                events.append(("end", corner))
        return {t: (dict(dead if corner.startswith("ss") else ok), None) for t in temps}

    real, workers, budget = sim.startup_corner, sim.WORKERS, sim.budget
    sim.startup_corner, sim.WORKERS = fake, 2
    seen = []
    sim.budget = lambda seconds=None: seen.append(budget(seconds)) or seen[-1]
    try:
        groups = [(c, c, 1.0, None) for c in ("tt", "ff", "ss1", "ss2")]
        t0 = _t.time()
        got = P._checked_sweep(None, groups, [27], 20e-6, 300e-6, 150,
                               lambda key, coarse: any(P._odd(r) for r, e in coarse[key].values()))
        wall = _t.time() - t0
    finally:
        sim.startup_corner, sim.WORKERS, sim.budget = real, workers, budget
    assert peak[0] == 2, peak
    assert wall < 4 * 0.2 * 0.75, wall                          # 4 groups x 1 fine step of 0.2 s, 2 at a time
    last_ss = max(i for i, (k, c) in enumerate(events) if k == "end" and c.startswith("ss"))
    first_pass = min(i for i, (k, c) in enumerate(events) if k == "start" and c in ("tt", "ff"))
    assert last_ss < first_pass, events
    assert list(got) == ["tt", "ff", "ss1", "ss2"] and all(got[c][27][1] is None for c in got)
    sus, rest = seen
    assert sim.SUSPECT_BUDGET - sus["left"] >= 2 * 0.2 * 0.9 and sim.FINE_BUDGET - rest["left"] >= 2 * 0.2 * 0.9   # (run seconds, not wall)


def test_settle_time_from_a_waveform():
    t = [i * 1e-6 for i in range(101)]                                    # 0 .. 100 us
    v = {"out": [min(1.0, x / 30e-6) for x in t], "v1#branch": [1e-5] * 101}
    assert abs(sim.settle_time(t, v, ["v1#branch"], 20e-6) - 30e-6) < 1.5e-6  # reaches 1 V at 30 us, stays there
    v["out"][95] = 0.5                                                    # moves again late: not settled
    assert sim.settle_time(t, v, ["v1#branch"], 20e-6) is None


def test_windowed_fine_check_confirms_an_early_settling_power_up():
    """Our reference with its start-up device settles soon after the ramp: the first fine check runs over a window,
    not the whole hold, and the result is the same one the default step found."""
    tb = sim.Testbench(sch="own.sch", circuit=BETA + STARTUP, analyses=[".op"])
    coarse = sim.startup_corner(tb, "tt", [27], 1.0, 20e-6, 300e-6, 150)     # as _checked_sweep passes it
    assert coarse[27][0]["settled_at"] is not None
    r, e = sim.startup_checked(tb, "tt", [27], 1.0, ramp=20e-6, settle=300e-6, coarse=coarse)[27]
    assert e is None and "over the first" in r["step_check"], (e, r and r.get("step_check"))
    assert "_wave" not in r and r["i_end"] > 1e-6


def test_a_cut_session_keeps_the_conditions_that_finished():
    """A power-up session cut by its time limit (or the review's budget) after some temperatures finished keeps
    those: each wrote its own files. Here the cut is staged after the second of three: the real deck runs, then the
    last temperature's file is removed and the run reports a timeout."""
    import re
    tb = sim.Testbench(sch="own.sch", circuit=BETA + STARTUP, analyses=[".op"])
    full = sim.startup_corner(tb, "tt", [-40, 27, 125], 1.0, ramp=20e-6, settle=300e-6)
    real = sim.run

    def cut(deck, timeout=120):
        out, err = real(deck, timeout)
        m = re.search(r">> (\S+)/tr2\.txt", deck)
        if not m:                                        # (the other runs: not the power-up session)
            return out, err
        os.remove(os.path.join(m.group(1), "tr2.txt"))
        return "", "timeout"
    sim.run = cut
    try:
        part = sim.startup_corner(tb, "tt", [-40, 27, 125], 1.0, ramp=20e-6, settle=300e-6)
    finally:
        sim.run = real
    assert part[125] == (None, "timeout"), part[125]
    for t in (-40, 27):
        r, e = part[t]
        assert e is None and abs(r["i_end"] - full[t][0]["i_end"]) < 1e-12, (t, part[t], full[t])
        for n, (a, b) in full[t][0]["nodes"].items():     # (the file copy prints more digits than meas does)
            assert abs(r["nodes"][n][0] - a) < 1e-5 and abs(r["nodes"][n][1] - b) < 1e-5, (n, r["nodes"][n], a, b)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

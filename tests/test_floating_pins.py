"""A power-up test leaves some pins undriven (the no-model baseline has no bias for them). A floating pin that keeps
moving is not an unstable loop: reported as an untested input (info), never as an oscillation. No simulation."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks, plan as P  # noqa: E402

BASE = dict(i_op=1e-5, i_end=1e-5, i_prev=1e-5, nodes={"x": (0.5, 0.5)}, confirmed=True, ramp=20e-6, settle=300e-6)


def sweep(swing):
    return {("tt", 27, 1.0): (dict(BASE, swing=swing), None), ("ss", 27, 1.0): (dict(BASE), None)}


def test_swing_only_on_an_undriven_pin_is_not_an_oscillation():
    f = checks.startup(sweep({"INPUT": 0.078}), floating=["input", "sel"])
    assert [x["rule"] for x in f] == ["analog/floating_input"] and f[0]["severity"] == "info", f
    assert "not driven" in f[0]["message"] and "Give INPUT a bias" in f[0]["message"]


def test_swing_on_an_internal_node_is_still_an_oscillation():
    f = checks.startup(sweep({"INPUT": 0.2, "vout": 0.44}), floating=["input"])
    assert [x["rule"] for x in f] == ["analog/oscillates"] and f[0]["device"] == "vout", f
    assert "left input undriven" in f[0]["message"] and "bias it to confirm" in f[0]["message"], f[0]["message"]
    assert f[0]["severity"] == "warn"                  # an oscillation stays a warning (backtest row 8's op-amp)
    plain = checks.startup(sweep({"INPUT": 0.078}))                                    # (no floating list)
    assert [x["rule"] for x in plain] == ["analog/oscillates"] and "undriven" not in plain[0]["message"]


def test_undriven_pins_of_a_plan():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "c.spice"), "w").write(".subckt amp vdd vss inp inn out en\nR1 vdd out 1k\n.ends\n")
    plan = dict(cell="c.spice#amp", kind="powerup", supplies={"vdd": 1.8}, grounds=["vss"],
                controls=[{"port": "en", "volts": 1.8}], loads=[{"port": "out", "farads": 1e-12}])
    assert P.undriven(plan, d) == ["inp", "inn"]


def test_no_startup_with_undriven_inputs_does_not_claim_a_missing_startup_circuit():
    dead = dict(BASE, i_end=1e-10, i_prev=1e-10)
    sw = {("tt", 27, 1.0): (dead, None)}
    f, = checks.startup(sw, floating=["inp", "inn"])
    assert f["rule"] == "analog/no_startup" and "inn, inp undriven" in f["message"]
    assert "needs a start-up circuit" not in f["message"]
    g, = checks.startup(sw)
    assert "it needs a start-up circuit" in g["message"]
    assert f["severity"] == "info" and g["severity"] == "warn"     # the undriven inputs alone can hold it off


def test_marginal_startup_with_undriven_inputs_is_a_note():
    sw = {("tt", 27, 1.0): (None, "undetermined: the power-up result changes with the simulator's time step (1 V at "
                                  "2 ns, 0 V at 1 ns)")}
    f, = checks.startup(sw, floating=["inp"])
    assert f["rule"] == "analog/marginal_startup" and f["severity"] == "info" and "left inp undriven" in f["message"]
    g, = checks.startup(sw)
    assert g["severity"] == "warn" and "undriven" not in g["message"]


def test_pins_that_reach_only_each_other_are_undriven():
    """A pass gate's two terminals have a DC path, but only to each other: with nothing the test drives in their
    group, both float (backtest row 12's analog switch)."""
    d = tempfile.mkdtemp()
    open(os.path.join(d, "c.spice"), "w").write(
        ".subckt pg z a gp gn vss vcc\nXM1 z gn a vss sky130_fd_pr__nfet_01v8 L=0.2 W=2\n"
        "XM2 z gp a vcc sky130_fd_pr__pfet_01v8 L=0.2 W=2\n.ends\n"
        ".subckt sw out in en vss vcc mon\nx2 out in enb en vss vcc pg\nXM3 enb en vcc vcc sky130_fd_pr__pfet_01v8 L=0.2 W=1\n"
        "XM4 enb en vss vss sky130_fd_pr__nfet_01v8 L=0.2 W=1\nR1 mon vss 1k\n.ends\n")
    plan = dict(cell="c.spice#sw", kind="powerup", supplies={"vcc": 1.8}, grounds=["vss"],
                controls=[{"port": "en", "volts": 1.8}])
    assert P.undriven(plan, d) == ["out", "in"]          # mon reaches ground through R1: driven
    plan["biases"] = [{"port": "in", "volts": 0.9}]
    assert P.undriven(plan, d) == []                      # in is held, and out reaches it through the switch
    # a poly resistor's body pin carries no DC: a pin behind one to the substrate only still floats
    open(os.path.join(d, "r.spice"), "w").write(".subckt rr vdd vss a b\nXR1 a b vss sky130_fd_pr__res_xhigh_po_5p73 L=8\n"
                                                "R2 vdd vss 1k\n.ends\n")
    assert P.undriven(dict(cell="r.spice#rr", kind="powerup", supplies={"vdd": 1.8}, grounds=["vss"]), d) == ["a", "b"]


def _held(swings):
    """held_inputs on a stub simulator: `swings` {held volts: swing dict or None}. Returns (findings, benches seen)."""
    d = tempfile.mkdtemp()
    open(os.path.join(d, "c.spice"), "w").write(".subckt amp vdd vss inp out\nR1 vdd out 1k\n.ends\n")
    plan = dict(cell="c.spice#amp", kind="powerup", supplies={"vdd": 1.8}, grounds=["vss"], loads=[])
    f = checks.startup(sweep({"out": 0.3}), floating=["inp"])
    seen, old = [], P.sim.startup_checked

    def fake(tb, c, temps, v, **kw):
        line = next(l for l in tb.circuit.splitlines() if l.startswith("Vbias"))
        volts = float(line.split()[-1])
        seen.append((c, temps, v, line))
        sw = swings.get(volts)
        return {temps[0]: (dict(BASE, swing=sw) if sw else dict(BASE), None) if sw != "error" else (None, "timeout")}
    P.sim.startup_checked = fake
    try:
        return P.held_inputs(plan, d, f, ["inp"], 20e-6, 300e-6, 150), seen
    finally:
        P.sim.startup_checked = old


def test_oscillation_gone_with_the_input_held_is_a_note():
    (f,), seen = _held({})
    assert [s[3] for s in seen] == ["Vbias0 inp 0 0", "Vbias0 inp 0 0.9", "Vbias0 inp 0 1.8"], seen
    assert all(s[0] == "tt" and s[1] == [27] for s in seen)           # the oscillation's own worst condition
    assert f["rule"] == "analog/oscillates" and f["severity"] == "info", f
    assert "held at 0 / 0.9 / 1.8 V the circuit settles every time" in f["message"], f["message"]
    assert "a loop is unstable" not in f["message"] and [x["state"] for x in f["held"]] == ["settled"] * 3


def test_oscillation_that_survives_a_held_input_stays_a_warning():
    (f,), _ = _held({0.9: {"out": 0.25}})
    assert f["severity"] == "warn" and "held at 0.9 V it still leaves out swinging 250 mV" in f["message"], f["message"]
    (g,), _ = _held({1.8: "error"})                                   # one level did not finish: nothing concluded
    assert g["severity"] == "warn" and "at 0 V it settles; at 0.9 V it settles; at 1.8 V it did not finish (timeout)" \
        in g["message"] and "Nothing is concluded" in g["message"], g["message"]


def test_held_reruns_have_their_own_time():
    """Inside a review whose budget is spent, the held re-runs still get HELD_BUDGET seconds."""
    left = []
    old = P.sim.startup_checked
    P.sim.startup_checked = lambda tb, c, temps, v, **kw: (left.append(P.sim.time_left()), {temps[0]: (dict(BASE), None)})[1]
    try:
        d = tempfile.mkdtemp()
        open(os.path.join(d, "c.spice"), "w").write(".subckt amp vdd vss inp out\nR1 vdd out 1k\n.ends\n")
        plan = dict(cell="c.spice#amp", kind="powerup", supplies={"vdd": 1.8}, grounds=["vss"], loads=[])
        with P.sim.until(0.01):
            P.held_inputs(plan, d, checks.startup(sweep({"out": 0.3}), floating=["inp"]), ["inp"], 20e-6, 300e-6, 150)
        assert len(left) == 3 and all(x > P.HELD_BUDGET - 5 for x in left), left
        left.clear()
        P.held_inputs(plan, d, checks.startup(sweep({"out": 0.3}), floating=["inp"]), ["inp"], 20e-6, 300e-6, 150)
        assert left == [None] * 3                       # no review budget: none imposed here
    finally:
        P.sim.startup_checked = old


def test_no_held_rerun_without_undriven_inputs():
    f = checks.startup(sweep({"out": 0.3}))
    assert P.held_inputs(dict(supplies={"vdd": 1.8}), "/nonexistent", f, [], 20e-6, 300e-6, 150) == f


def test_a_real_power_up_keeps_an_undriven_pin_out_of_the_state(tmp_path=None):
    """ngspice + sky130 on our own subcircuit: pin inp drives only a gate, nothing drives it. Its node is not part of
    the measured state, so it can neither make a finding nor a step-check disagreement."""
    d = tempfile.mkdtemp()
    open(os.path.join(d, "c.spice"), "w").write(
        ".subckt cell vdd vss inp out\nR1 vdd out 10k\nR2 out vss 10k\n"
        "XM1 x inp vss vss sky130_fd_pr__nfet_01v8 L=1 W=1\nR3 vdd x 100k\n.ends\n")
    plan = dict(cell="c.spice#cell", kind="powerup", supplies={"vdd": 1.8}, grounds=["vss"], loads=[],
                corners=["tt"], temps=[27], vscales=[1.0])
    r = P.run(plan, d)
    assert r["ok"], r
    row, = r["results"]
    assert row["error"] is None, row
    assert "inp" not in row["nodes"] and "out" in row["nodes"], row["nodes"]
    assert not [f for f in r["findings"] if f["severity"] != "info"], r["findings"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

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

"""The feedback loops a designer closed in a testbench (kaaval_engine.loops): found from the netlist and the symbols'
pin directions, cut at the instance's output, measured by Tian's method. Our own two-stage op-amp as a subcircuit in
a follower testbench: a thin compensation capacitor is flagged and a good one is not; the testbench's own AC source
and a spare copy on nets of its own change nothing."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks, loops, sim  # noqa: E402

AMP = """.subckt amp vdd inn inp out
Ib vdd vb 20u
XM6 vb vb 0 0 sky130_fd_pr__nfet_01v8 L=1 W=4 nf=1 m=1
XM5 tail vb 0 0 sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
XM1 o1 inn tail 0 sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
XM2 o2a inp tail 0 sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
XM3 o1 o1 vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=8 nf=1 m=1
XM4 o2a o1 vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=8 nf=1 m=1
XM7 out o2a vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=32 nf=1 m=1
XM8 out vb 0 0 sky130_fd_pr__nfet_01v8 L=1 W=16 nf=1 m=1
Cc o2a ncz {cc}
Rz ncz out 2k
.ends amp"""
DIRS = {"x1": ["inout", "in", "in", "out"], "x2": ["inout", "in", "in", "out"]}


def bench(cc, vin="Vin inp 0 0.9", spare=False):
    return (AMP.replace("{cc}", cc) + "\nVdd vdd 0 1.8\n" + vin + "\nx1 vdd fb inp out amp\nRfb out fb 1\nCL out 0 10p\n"
            + ("x2 n0 n1 n2 n3 amp\n" if spare else ""))


def test_loops_are_found_from_pin_directions():
    f = loops.find(bench("2p"), DIRS)
    assert f == [dict(inst="x1", net="out", pin="x1.4", via="back to its pin 2 (fb) through Rfb")], f
    # a path through a net a source holds is no feedback: out -> R -> a reference, not back to the input
    assert loops.find(bench("2p").replace("Rfb out fb 1", "Rfb out ref 1\nVref ref 0 0.9\nRb ref fb 1k"), DIRS) == []
    # wired straight back, and a symbol with every pin inout (no direction to go by)
    g = loops.find(bench("2p").replace("x1 vdd fb inp out amp\nRfb out fb 1", "x1 vdd out inp out amp"),
                   {"x1": ["inout"] * 4})
    assert [(x["net"], x["via"]) for x in g] == [("out", "back to its pin 4 (out) directly")], g


def test_testbench_ac_source_and_spare_copy_are_left_out():
    assert loops.no_ac("Vin inp 0 0.9 AC 1 pulse 0 1 0 1n 1n 1u 2u\nR1 a b 1k").splitlines()[0] == \
        "Vin inp 0 0.9 pulse 0 1 0 1n 1n 1u 2u"
    kept = loops.connected(bench("2p", spare=True), "x1")
    assert "x2 n0 n1 n2 n3 amp" not in kept and "x1 vdd fb inp out amp" in kept and ".subckt amp" in kept


def margins(circuit):
    tb = sim.Testbench(sch="own.sch", circuit=circuit, analyses=[".op"])
    lp, = loops.find(circuit, DIRS)
    r, e = loops.sweep(tb, lp, corners=["tt"], conds=[(27, 1.0)])[("tt", 27, 1.0)]
    assert not e, e
    return r


def test_thin_margin_in_the_designers_follower_is_flagged():
    thin, good = margins(bench("0.3p")), margins(bench("3p"))
    assert thin["pm"] < 45 < good["pm"], (thin["pm"], good["pm"])
    assert [f["rule"] for f in checks.stability({("tt", 27, 1.0): (thin, None)})] == ["analog/low_phase_margin"]
    assert checks.stability({("tt", 27, 1.0): (good, None)}) == []
    # the testbench's AC stimulus and a spare amplifier on floating nets do not change the loop's margins
    noisy = margins(bench("0.3p", vin="Vin inp 0 0.9 AC 1", spare=True))
    assert abs(noisy["pm"] - thin["pm"]) < 0.5, (noisy["pm"], thin["pm"])


def test_review_reports_each_loop_once():
    """runner.testbench_loops on a stub engine: the same op-amp in the same feedback in two testbenches is one
    finding, worded with where the loop is."""
    from app import runner
    got, events = [], []
    loop = dict(inst="x1", subckt="opamp", net="VOUT", pin="x1.2", via="back to its pin 4 (VOUT) directly",
                results=[dict(pm=1.0), dict(pm=34.0)],
                findings=[dict(rule="analog/low_phase_margin", severity="warn", message="The loop has thin margins.")])
    old = runner.engine.loops, runner.store.add_finding, runner.store.event
    runner.engine.loops = lambda ws, rel, budget=None: {"loops": [dict(loop)]}
    runner.store.add_finding = lambda rid, f: got.append(f)
    runner.store.event = lambda rid, stage, msg, level="info": events.append(msg)
    try:
        assert runner.testbench_loops("r", "ws", ["a/tb1.sch", "a/tb2.sch"]) == 1
    finally:
        runner.engine.loops, runner.store.add_finding, runner.store.event = old
    f, = got
    assert f["rule"] == "analog/low_phase_margin" and f["location"] == "a/tb1.sch · x1 loop (cut at x1.2)", f
    assert f["title"].startswith("In the designer's own testbench, x1 (opamp) in feedback, its output VOUT back to")
    assert any("phase margin 1–34°" in e for e in events) and any("same in 2 testbenches" in e for e in events), events

def test_the_loop_deck_prints_the_engines_phase_margin():
    """The evidence deck runs as plain ngspice and computes the same margin the engine reports."""
    import re
    circuit = bench("0.3p")
    tb = sim.Testbench(sch="own.sch", circuit=circuit, analyses=[".op"])
    lp, = loops.find(circuit, DIRS)
    r, e = loops.sweep(tb, lp, corners=["tt"], conds=[(27, 1.0)])[("tt", 27, 1.0)]
    out, err = sim.run(loops.deck(tb, lp, "tt", 27, 1.0), timeout=120)
    pm = float(re.search(r"^pm = (\S+)", out, re.M).group(1))
    assert not err and abs(pm - r["pm"]) < 0.2, (pm, r["pm"], err)

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

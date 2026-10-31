"""The circuit as drawn against the circuit as simulated, on our own one-transistor cell (tests/test_layout_check.py):
the schematic's power-up plan runs again, unchanged, on the layout extracted with its capacitances, and the results
are compared condition by condition. The comparison rules need no tools; the real run needs Magic and ngspice."""
import os, re, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
from kaaval_engine import extract, layout_check, plan as P, postlayout as PL  # noqa: E402
import test_layout_check as T  # noqa: E402


def row(**kw):
    return dict(dict(corner="tt", temp=27, vscale=1.0, error=None, i_op=1e-5, i_end=1e-5, nodes={"out": (0.9, 0.9)},
                     swing={}), **kw)


def test_compare_rules():
    assert PL.compare("powerup", [row()], [row(i_end=1.1e-5)]) == []                      # 10 %: the same
    d, = PL.compare("powerup", [row()], [row(i_end=1e-10)])
    assert d["what"] == "state" and (d["schematic"], d["layout"]) == ("settled", "dead")
    d, = PL.compare("powerup", [row()], [row(nodes={"out": (0.9, 0.6)})])
    assert d["what"] == "out after power-up"
    d, = PL.compare("stability", [dict(row(), pm=60.0, ugf=1e7)], [dict(row(), pm=41.0, ugf=1e7)])
    assert d["what"] == "phase margin"
    assert PL.compare("powerup", [row()], [row(error="unconfirmed: ...", i_end=0)]) == []   # not completed: no claim
    f = PL.finding("amp", "stability", [d], 30)
    assert f["rule"] == "layout/post_layout_differs" and "60° in the schematic, 41° as drawn" in f["title"]


def test_as_drawn_matches_as_simulated_for_one_transistor():
    if not layout_check.available():
        print("skip: Magic or Netgen not installed")
        return
    d = T._repo()
    pair, = layout_check.pairs(d)
    text, err = extract.cell(d, pair["cell"], pair["mag"], parasitics=True)
    assert text and re.search(r"(?m)^C\d+ ", text), err                  # the layout's capacitances are in it
    os.makedirs(os.path.join(d, PL.OUT))
    open(os.path.join(d, PL.post_path(pair["cell"])), "w").write(text)
    plan = dict(cell=pair["sch"], kind="powerup", supplies={"D": 1.8}, grounds=["S"],
                controls=[{"port": "G", "volts": 1.8}], loads=[], corners=["tt"], temps=[27], vscales=[1.0])
    a = P.run(plan, d)
    b = P.run(dict(plan, cell=PL.post_cell(pair["cell"])), d)
    assert a["ok"] and b["ok"], (a, b)
    assert a["results"][0]["i_end"] > 1e-5, a["results"]                   # the transistor conducts
    assert PL.compare("powerup", a["results"], b["results"]) == [], (a["results"], b["results"])


def test_runner_compares_only_tests_that_drive_every_input():
    """Stubbed engine: two planned tests on cells whose layout matched; only the one with every input driven is
    re-run as drawn, and its disagreement becomes a finding; the other is said to be not compared."""
    from app import runner
    import tempfile
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "x"))
    for c, body in (("drv", "R1 vdd out 1k\nR2 out vss 1k"), ("flt", "XM1 out inp vss vss sky130_fd_pr__nfet_01v8 L=1 W=1")):
        open(os.path.join(d, "x", f"{c}.spice"), "w").write(f".subckt {c} vdd vss inp out\n{body}\n.ends\n")
    plans = [dict(plan=dict(cell=f"x/{c}.spice#{c}", kind="powerup", supplies={"vdd": 1.8}, grounds=["vss"],
                            biases=[{"port": "inp", "volts": 0.9}] if c == "drv" else []),
                  ok=True, results=[row()]) for c in ("drv", "flt")]
    lay = [dict(sch=f"x/{c}.spice#{c}", cell=c, mag=f"m/{c}.mag", verdict="match") for c in ("drv", "flt")]

    class LV:
        d = {"plan_results": plans}
    ran, events, finds = [], [], []
    saved = (runner.extract.cell, runner.engine.upload, runner.engine.plan, runner.store.event, runner.store.add_finding)
    runner.extract.cell = lambda root, cell, mag, parasitics=False: ("* post\n", None)
    runner.engine.upload = lambda files: "ws2"
    runner.engine.plan = lambda ws, ep: ran.append(ep["cell"]) or dict(ok=True, results=[row(i_end=1e-10)])
    runner.store.event = lambda rid, st, msg, lvl="info": events.append(msg)
    runner.store.add_finding = lambda rid, f: finds.append(f)
    try:
        runner.post_layout("r", LV(), d, {}, lay)
    finally:
        (runner.extract.cell, runner.engine.upload, runner.engine.plan, runner.store.event,
         runner.store.add_finding) = saved
    assert ran == [PL.post_cell("drv")], ran
    assert [f["rule"] for f in finds] == ["layout/post_layout_differs"]
    assert any("Not compared as drawn (1 cell(s))" in e and "inp" in e for e in events), events


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

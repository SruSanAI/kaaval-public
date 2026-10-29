"""Kaaval's power-up sequence check on a circuit of our own, simulated with ngspice and the sky130 models.

A beta-multiplier reference runs on the 1.8 V rail, and its only start-up is a capacitor kick from the 3.3 V rail: a
cross-domain start-up. Powered with every rail together it starts, so the plain power-up check passes. When the 3.3 V
rail is up first and the 1.8 V rail follows long enough later, the kick has drained away before the core has a supply: the
reference stays off. The sequence check must find exactly that, and nothing when the core has its own start-up."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks, plan as P

CORE = """.subckt bref2 vdd avdd vss iout
XM1 n1 n1 vss vss sky130_fd_pr__nfet_01v8 L=2 W=4 nf=1 m=1
XM2 n2 n1 s2 vss sky130_fd_pr__nfet_01v8 L=2 W=16 nf=1 m=1
R1 s2 vss 20k
XM3 n1 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM4 n2 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM5 iout n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
{startup}
.ends
"""
KICK = "Ckick avdd n1 200f"
OWN = "XM6 n1 vss vdd vdd sky130_fd_pr__pfet_01v8 L=20 W=0.42 nf=1 m=1"


def plan(**kw):
    return {**dict(cell="ref.spice#bref2", kind="sequence", supplies={"vdd": 1.8, "avdd": 3.3}, grounds=["vss"],
                   pads=[{"port": "iout"}], corners=["tt"], temps=[27], vscales=[1.0]), **kw}


def write(tmp_path, startup):
    (tmp_path / "ref.spice").write_text(CORE.format(startup=startup))
    return str(tmp_path)


def test_cases_cover_order_speed_and_controls():
    names = [n for n, _, _ in P.cases(plan())]
    assert names[0].startswith("rails together, fast") and len(names) == 2 * (1 + 2 * len(P.GAPS))
    assert any("avdd first, others 1000 µs later, slow" in n for n in names)
    sched = {n: s for n, s, _ in P.cases(plan(controls=[{"port": "iout", "volts": 1.8}]))}
    late = [s for n, s in sched.items() if "after the rails" in n]
    assert len(sched) == 28 and all(s["vctl0"][0] >= max(s["vplan0"][0], s["vplan1"][0]) for s in late)


def test_validation_names_bad_ports(tmp_path):
    root = write(tmp_path, KICK)
    errs = P.validate(plan(controls=[{"port": "nope", "volts": 1.8}], pads=[{"port": "nada"}]), root)
    assert any("control port 'nope'" in e for e in errs) and any("pad port 'nada'" in e for e in errs)
    assert P.validate(plan(corners=checks.CORNERS, temps=checks.TEMPS, vscales=[0.9, 1.0]), root)  # 14 x 30 > 128


def test_cross_domain_kick_fails_when_the_3v3_rail_comes_first(tmp_path):
    r = P.run(plan(), write(tmp_path, KICK))
    assert r["ok"] and "Rpad0" in r["bench"]
    f = [x for x in r["findings"] if x["rule"] == "analog/sequence_dependent"]
    assert len(f) == 1 and f[0]["case"].startswith("rails avdd first"), r["findings"]
    # the finding states the gap at which it starts failing, not one chosen gap
    seq = f[0]["sequence"]
    assert seq["lead"] == "avdd" and seq["fail_gap"] > (seq["pass_gap"] or 0) and "µs or more" in f[0]["message"]
    together = [x for x in r["results"] if x["case"] == r["cases"][0]]
    assert all(x["state"] == "settled" and x["i_end"] > 5e-6 for x in together)


def test_own_startup_passes_every_sequence(tmp_path):
    r = P.run(plan(), write(tmp_path, OWN))
    assert r["ok"] and r["findings"] == [], r["findings"]


if __name__ == "__main__":
    import inspect, pathlib, tempfile
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(*([pathlib.Path(tempfile.mkdtemp())] if inspect.signature(fn).parameters else []))
            print("ok", name)

"""Kaaval's cross-domain overstress check on circuits of our own (ngspice + sky130): a 1.8 V (thin-oxide) device must
never see much more than 1.8 V between its terminals, with every rail on or with one rail still off.

A  a 3.3 V inverter drives a 1.8 V inverter's gates directly (no level shifter): overstressed with every rail on.
B  the same, received by thick-oxide (5 V) devices: nothing to report.
C  a 1.8 V switch with a 3.3 V pull-up: fine while the 1.8 V rail holds its gate on; overstressed when the 1.8 V rail
   is off and the 3.3 V rail is up, the state every two-rail chip passes through during power-up."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks, plan as P, sim

HV = "sky130_fd_pr__{}fet_g5v0d10v5 L=0.5 W=1 nf=1 m=1"
LV = "sky130_fd_pr__{}fet_01v8 L=0.15 W=1 nf=1 m=1"
A = f""".subckt cross vdd avdd vss in out
XH1 mid in avdd avdd {HV.format('p')}
XH2 mid in vss vss {HV.format('n')}
XL1 out mid vdd vdd {LV.format('p')}
XL2 out mid vss vss {LV.format('n')}
.ends
"""
B = A.replace(f"XL1 out mid vdd vdd {LV.format('p')}", f"XL1 out mid vdd vdd {HV.format('p')}") \
     .replace(f"XL2 out mid vss vss {LV.format('n')}", f"XL2 out mid vss vss {HV.format('n')}")
C = f""".subckt cross vdd avdd vss in out
R1 avdd out 100k
XL1 out vdd vss vss {LV.format('n')}
R2 in vss 1meg
.ends
"""


def plan(**kw):
    return {**dict(cell="x.spice#cross", kind="domains", supplies={"vdd": 1.8, "avdd": 3.3}, grounds=["vss"],
                   biases=[{"port": "in", "volts": 0.0}], corners=["tt", "ff"], temps=[27], vscales=[1.0]), **kw}


def run(tmp_path, text):
    (tmp_path / "x.spice").write_text(text)
    return P.run(plan(), str(tmp_path))


def test_models_resolve_through_the_hierarchy():
    m = sim.device_models(A + "Xdut a b c d e cross")
    assert m["xdut.xl2"] == "sky130_fd_pr__nfet_01v8" and m["xdut.xh1"] == "sky130_fd_pr__pfet_g5v0d10v5", m
    assert checks.rating(m["xdut.xl2"]) == (1.8, 1.8) and checks.rating("sky130_fd_pr__res_xhigh_po") is None


def test_missing_level_shifter_overstresses_the_1v8_gates(tmp_path):
    r = run(tmp_path, A)
    f = [x for x in r["findings"] if x["rule"] == "analog/overstress"]
    assert r["ok"] and len(f) == 1, r
    assert f[0]["device"].endswith(("xl1", "xl2")) and f[0]["volts"] > 3.0 and \
        any(s.startswith("all rails on") for s in f[0]["states"]), f[0]


def test_thick_oxide_receiver_passes(tmp_path):
    r = run(tmp_path, B)
    assert r["ok"] and r["findings"] == [], r["findings"]


def test_overstress_only_while_the_1v8_rail_is_off(tmp_path):
    r = run(tmp_path, C)
    f = [x for x in r["findings"] if x["rule"] == "analog/overstress"]
    assert len(f) == 1 and f[0]["states"] == ["vdd off, avdd on (supply x1)"], r["findings"]
    assert f[0]["volts"] > 3.0, f[0]


if __name__ == "__main__":
    import inspect, pathlib, tempfile
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(*([pathlib.Path(tempfile.mkdtemp())] if inspect.signature(fn).parameters else []))
            print("ok", name)

"""Kaaval's pad drive test on circuits of our own (ngspice + sky130): an output that leaves the chip through a Tiny
Tapeout pad must hold its value with what the board hangs on it. The load is swept (open, 10 Mohm, 1 Mohm, 100 kohm,
10 kohm); TT's demo-board guide asks for pull-downs of at least 1 Mohm, so that is the load judged.

weak    a 0.9 V reference from a 100k / 100k divider (50 kohm output resistance): 1 Mohm moves it about 5 %
strong  the same reference from a 1k / 1k divider (500 ohm): nothing to report"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import plan as P

REF = """.subckt ref vdd vss vref
R1 vdd vref {r}
R2 vref vss {r}
.ends
"""


def run(tmp_path, r):
    (tmp_path / "r.spice").write_text(REF.format(r=r))
    return P.run(dict(cell="r.spice#ref", kind="drive", supplies={"vdd": 1.8}, grounds=["vss"], pads=[{"port": "vref"}],
                      corners=["tt"], temps=[27], vscales=[1.0]), str(tmp_path))


def test_high_impedance_reference_is_weak(tmp_path):
    r = run(tmp_path, "100k")
    f = [x for x in r["findings"] if x["rule"] == "analog/weak_output"]
    assert r["ok"] and len(f) == 1, r
    assert 40e3 < f[0]["rout"] < 60e3 and abs(f[0]["volts"][0] - 0.9) < 0.01, f[0]


def test_low_impedance_reference_passes(tmp_path):
    r = run(tmp_path, "1k")
    assert r["ok"] and r["findings"] == [], r["findings"]


def test_drive_needs_a_pad(tmp_path):
    (tmp_path / "r.spice").write_text(REF.format(r="1k"))
    errs = P.validate(dict(cell="r.spice#ref", kind="drive", supplies={"vdd": 1.8}, grounds=["vss"]), str(tmp_path))
    assert any("pad port" in e for e in errs), errs


if __name__ == "__main__":
    import inspect, pathlib, tempfile
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(*([pathlib.Path(tempfile.mkdtemp())] if inspect.signature(fn).parameters else []))
            print("ok", name)

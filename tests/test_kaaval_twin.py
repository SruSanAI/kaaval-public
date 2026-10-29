"""Silicon Twin on circuits of our own (ngspice + sky130): measured values are explained by the chip context that
reproduces them, and the kind of explanation is right.

divider    a 0.9 V reference with 50 kohm output resistance: "0.9 V" is the unloaded DC answer, "0.6 V" the DC answer
           under a 100 kohm load: both readings are the load's doing
no start   a self-biased reference without a start-up device: a chip that reads 0 V on its output came up in its
           zero-current state; the DC answer is not 0, so this is a power-up explanation"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import twin

DIV = """.subckt ref vdd vss vref
R1 vdd vref 100k
R2 vref vss 100k
.ends
"""
BREF = """.subckt bref vdd vss iout
XM1 n1 n1 vss vss sky130_fd_pr__nfet_01v8 L=2 W=4 nf=1 m=1
XM2 n2 n1 s2 vss sky130_fd_pr__nfet_01v8 L=2 W=16 nf=1 m=1
R1 s2 vss 20k
XM3 n1 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM4 n2 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM5 iout n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
R2 iout vss 50k
.ends
"""


def test_divider_readings_are_load_effects(tmp_path):
    (tmp_path / "r.spice").write_text(DIV)
    res = twin.search(dict(cell="r.spice#ref", supplies={"vdd": 1.8}, grounds=["vss"], node="vref",
                           measured=[0.9, 0.6]), str(tmp_path), corners=["tt"], loads=[None, 1e5])
    assert res["ok"] and not res["unmatched"], res
    by = {m["measured"]: m for m in res["matches"]}
    assert by[0.9]["how"] == "dc" and by[0.9]["load"] is None and by[0.6]["how"] == "dc" and by[0.6]["load"] == 1e5


def test_zero_reading_is_a_powerup_state(tmp_path):
    (tmp_path / "b.spice").write_text(BREF)
    res = twin.search(dict(cell="b.spice#bref", supplies={"vdd": 1.8}, grounds=["vss"], node="iout", pad=False,
                           measured=[0.0]), str(tmp_path), corners=["tt"], temps=(-40,), loads=[None])
    assert res["ok"] and res["matches"] and res["matches"][0]["how"] == "powerup", res
    assert "another operating point" in " ".join(twin.explain(res))


if __name__ == "__main__":
    import inspect, pathlib, tempfile
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(*([pathlib.Path(tempfile.mkdtemp())] if inspect.signature(fn).parameters else []))
            print("ok", name)

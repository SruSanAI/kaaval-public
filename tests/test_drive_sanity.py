"""The drive check on readings like those of backtest v2 (no simulation): an output that rises under load is no
finding; one that falls to 0 V under 10 MOhm is high impedance, not '2.4e8 MOhm'; a plain weak source keeps its
estimated resistance. Readings: [open, 10 MOhm, 1 MOhm, 100 kOhm, 10 kOhm] to ground."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import checks  # noqa: E402

C = ("tt", 27, 1.0)


def one(volts, **kw):
    return checks.drive({C: ({0: volts}, None)}, ["OUT"], **kw)


def test_rising_under_load_is_not_a_finding():
    assert one([0.679, 1.800, 1.797, 1.768, 1.509]) == []          # (was "-6.22e+05 Ohm output resistance")


def test_gone_under_10_megohm_is_high_impedance():
    f, = one([1.8, 0.0, 0.0, 0.0, 0.0])
    assert "nothing driving it (high impedance)" in f["message"] and f["rout"] == float("inf"), f["message"]


def test_weak_source_keeps_its_resistance():
    f, = one([1.799, 1.795, 1.752, 1.294, 0.172])
    assert "about 26.8 kΩ output resistance" in f["message"], f["message"]
    assert "undriven" not in f["message"]
    g, = one([1.799, 1.795, 1.752, 1.294, 0.172], floating=["inp", "inn"])
    assert "left inn, inp undriven" in g["message"]
    assert f["severity"] == "warn" and g["severity"] == "info"      # an undriven input decides the level: a note


def test_strong_output_passes():
    assert one([1.8, 1.8, 1.8, 1.799, 1.79]) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

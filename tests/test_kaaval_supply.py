"""The logic's real supply from an on-chip LDO (kaaval_engine.supply), on a regulator of our own: a 5-transistor
error amplifier and a PMOS pass device, 1.8 V in, 1.5 V out (ideal 0.75 V reference, divider of 2). Its lowest
output at ss names the setup library (the ss library at or below it), its highest at ff the hold library (the ff
library at or above it). When the input sags and the load grows, the LDO drops out below every library, and the report says so."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import supply

LDO = """.subckt ldo1 out vin vref vbn vss
XT tail vbn vss vss sky130_fd_pr__nfet_01v8 L=1 W=4 nf=1 m=1
X1 d1 fb tail vss sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
X2 g vref tail vss sky130_fd_pr__nfet_01v8 L=1 W=8 nf=1 m=1
X3 d1 d1 vin vin sky130_fd_pr__pfet_01v8 L=1 W=8 nf=1 m=1
X4 g d1 vin vin sky130_fd_pr__pfet_01v8 L=1 W=8 nf=1 m=1
XP out g vin vin sky130_fd_pr__pfet_01v8 L=0.5 W=200 nf=10 m=1
R1 out fb 100k
R2 fb vss 100k
C1 out vss 1n
.ends
"""
ARGS = (LDO, "ldo1", ["out", "vin", "vref", "vbn", "vss"], {"vin": 1.8}, ["vss"], "out")
BIAS = {"vref": 0.75, "vbn": 0.7}


def test_regulated_supply_names_the_libraries():
    r = supply.corner(*ARGS, loads=[10e-6, 1e-3], biases=BIAS, corners=["tt", "ss", "ff"], temps=[-40, 27, 125],
                      vscales=[1.0, 1.1])
    assert not r["errors"], r["errors"]
    s, h = r["setup"], r["hold"]
    assert 1.45 < s["volts"] < h["volts"] < 1.55, (s, h)
    assert s["lib"].startswith("sky130_fd_sc_hd__ss_") and s["lib"].endswith("1v44"), s
    assert h["lib"] == "sky130_fd_sc_hd__ff_n40C_1v56", h
    note = supply.sta_note(r)
    assert re.search(r"read_liberty .*sky130_fd_sc_hd__ss_\w+_1v44\.lib", note) and "droop" in note


def test_dropout_below_every_library_is_reported():
    r = supply.corner(*ARGS, loads=[1e-3, 5e-3], biases=BIAS, corners=["ss"], temps=[125], vscales=[0.9])
    s = r["setup"]
    assert s["at"][3] == 5e-3 and s["volts"] < 1.28, s          # 5 mA at ss 125 °C, 1.62 V in: out of regulation
    assert s["lib"] is None and "below every ss library" in s["note"], s       # no library is low enough: say so


def test_load_step_dip_names_a_lower_setup_library():
    """A 10 µA -> 1 mA step in 10 ns dips our LDO by ~0.1 V (1.502 -> 1.399 V at ss 27 °C, 1 nF on the output):
    below the 1.44 V library the DC answer picked, so setup with the step uses a lower one."""
    d, e = supply.droop(*ARGS, 10e-6, 1e-3, BIAS, "ss", 27, 1.0)
    assert e is None and 0.05 < d["droop"] < 0.2 and abs(d["after"] - d["before"]) < 0.02, (d, e)
    r = supply.corner(*ARGS, loads=[10e-6, 1e-3], biases=BIAS, corners=["ss"], temps=[27], vscales=[1.0],
                      step=(10e-6, 1e-3))
    st = r["setup_step"]
    lib_v = float(st["lib"].rsplit("_", 1)[1].replace("v", "."))
    assert st["volts"] < r["setup"]["volts"] and lib_v <= st["volts"] < 1.44, st
    assert "dips" in supply.sta_note(r)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

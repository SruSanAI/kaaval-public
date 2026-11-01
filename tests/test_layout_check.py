"""Layout against schematic on our own cell: a one-transistor layout drawn with Magic (tests/test_layout_extract.py)
and schematics of it. Drawn as simulated: a match; a schematic at another width: sizes differ; at another threshold
flavour (lvt): devices differ. The parsing tests need no tools; the rest run where Magic and Netgen are installed."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
from kaaval_engine import layout_check as L  # noqa: E402
import test_layout_extract as X  # noqa: E402

SYM = """v {xschem version=3.4.5 file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
E {}
B 5 -2.5 -2.5 2.5 2.5 {name=G dir=in}
B 5 97.5 -42.5 102.5 -37.5 {name=S dir=inout}
B 5 97.5 37.5 102.5 42.5 {name=D dir=inout}
"""


def sch(model="nfet_01v8", w=1, l=0.4):
    return f"""v {{xschem version=3.4.5 file_version=1.2}}
G {{}}
K {{}}
V {{}}
S {{}}
E {{}}
C {{sky130_fd_pr/{model}.sym}} 0 0 0 0 {{name=M1
W={w}
L={l}
nf=1
mult=1
model={model}
spiceprefix=X
}}
C {{devices/lab_pin.sym}} 20 -30 0 1 {{name=p1 lab=D}}
C {{devices/lab_pin.sym}} -20 0 0 0 {{name=p2 lab=G}}
C {{devices/lab_pin.sym}} 20 30 0 1 {{name=p3 lab=S}}
C {{devices/lab_pin.sym}} 20 0 0 1 {{name=p4 lab=VSUBS}}
C {{devices/ipin.sym}} -200 0 0 0 {{name=p5 lab=G}}
C {{devices/iopin.sym}} -200 40 0 0 {{name=p6 lab=S}}
C {{devices/iopin.sym}} -200 80 0 0 {{name=p7 lab=D}}
"""


def _repo(**kw):
    d = X._repo()
    open(os.path.join(d, "mag", "tt_um_kaaval_layout.sch"), "w").write(sch(**kw))
    open(os.path.join(d, "mag", "tt_um_kaaval_layout.sym"), "w").write(SYM)
    return d


REPORT = """Subcircuit summary:
Circuit 1: amp                             |Circuit 2: amp
-------------------------------------------|-------------------------------------------
sky130_fd_pr__nfet_01v8 (3)                |(no matching element)
(no matching element)                      |sky130_fd_pr__nfet_01v8_lvt (3)
sky130_fd_pr__res_xhigh_po_0p35 (1)        |sky130_fd_pr__res_xhigh_po (1)
sky130_fd_pr__pfet_01v8 (21->15)           |sky130_fd_pr__pfet_01v8 (13) **Mismat
Number of devices: 19 **Mismatch**         |Number of devices: 17 **Mismatch**
"""


def test_report_counts_and_differences():
    c = L.counts(REPORT)
    assert c["sky130_fd_pr__res_xhigh_po"] == [1, 1]                  # a fixed-width variant is the same resistor
    assert c["sky130_fd_pr__pfet_01v8"] == [15, 13]                   # after Netgen's merging (21 -> 15)
    d = L.differences(c)
    assert dict(kind="flavour", layout="sky130_fd_pr__nfet_01v8", schematic="sky130_fd_pr__nfet_01v8_lvt",
                n_layout=3, n_schematic=3) in d
    assert dict(kind="count", model="sky130_fd_pr__pfet_01v8", n_layout=15, n_schematic=13) in d and len(d) == 2


def test_small_size_differences_are_noted_not_warned():
    r = dict(verdict="sizes differ", cell="c", mag="c.mag", sch="c.sch",
             sizes=["R1: l 25 in the layout, 24.36 in the schematic"])
    assert L.finding(r)["severity"] == "info" and "up to 3 % off" in L.finding(r)["title"]
    r["sizes"].append("M1: l 0.5 in the layout, 1 in the schematic")
    assert L.finding(r)["severity"] == "warn"


def test_drawn_as_simulated_matches():
    if not L.available():
        print("skip: Magic or Netgen not installed")
        return
    d = _repo()
    p, = L.pairs(d)
    r = L.compare(d, p)
    assert r["match"] and r["verdict"] == "match" and L.finding(r) is None, r


def test_another_width_is_sizes_differ():
    if not L.available():
        return
    d = _repo(w=2)
    r = L.compare(d, L.pairs(d)[0])
    assert r["verdict"] == "sizes differ" and L.finding(r)["rule"] == "layout/sizes_differ", r


def test_another_threshold_flavour_is_devices_differ():
    if not L.available():
        return
    d = _repo(model="nfet_01v8_lvt")
    r = L.compare(d, L.pairs(d)[0])
    f = L.finding(r)
    assert r["verdict"] == "devices differ" and f and "threshold voltage" in f["title"], (r, f)


def test_review_reports_counts_and_findings():
    if not L.available():
        return
    d = _repo(model="nfet_01v8_lvt")
    res, fs, note = L.review(d)
    assert len(res) == 1 and [f["rule"] for f in fs] == ["layout/devices_differ"], (res, fs)
    assert "1 cell(s) drawn both ways; 0 match, 1 with different devices" in note, note
    assert L.review(X._repo()) == ([], [], "")                       # layout only: nothing to compare


def test_flatten_expands_the_design_hierarchy_to_devices():
    text = """.subckt inv a y vdd vss
XM1 y a vss vss sky130_fd_pr__nfet_01v8 L=0.5 W=1 ad='int((nf+1)/2) * W/nf * 0.29'
XM2 y a vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=2
.ends inv
.subckt buf a y vdd vss
x1 a mid vdd vss inv
x2 mid y vdd vss inv
.ends buf
"""
    flat = L.flatten(text, "buf").splitlines()
    assert flat[0] == ".subckt buf a y vdd vss" and flat[-1] == ".ends buf"
    assert "x1/XM1 mid a vss vss sky130_fd_pr__nfet_01v8 L=0.5 W=1 ad='int((nf+1)/2) * W/nf * 0.29'" in flat, flat
    assert "x2/XM2 y mid vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=2" in flat and len(flat) == 6


def test_dummies_are_recognised():
    flat = """.subckt c in out VDD VSS
X1 out in VSS VSS sky130_fd_pr__nfet_01v8 w=1 l=1
X2 out in VDD VDD sky130_fd_pr__pfet_01v8 w=1 l=1
X3 VSS VSS VSS VSS sky130_fd_pr__nfet_01v8 w=1 l=1
X4 n7 VSS n7 VDD sky130_fd_pr__pfet_01v8 w=1 l=1
X5 xd/OUT VSS VDD VDD sky130_fd_pr__pfet_01v8 w=1 l=1
X6 xd/OUT VSS VSS VSS sky130_fd_pr__nfet_01v8 w=1 l=1
.ends c"""
    # X3 off (gate on ground), X4 shorted channel, X5 / X6 an inverter driving nothing; X1 / X2 the real circuit
    assert L.off_devices(flat) == {"sky130_fd_pr__nfet_01v8": 2, "sky130_fd_pr__pfet_01v8": 2}


def test_an_empty_layout_view_is_not_compared():
    if not L.available():
        return
    d = _repo()
    mag = os.path.join(d, "mag", "tt_um_kaaval_layout.mag")
    text = open(mag).read()
    i, j = text.index("<< nmos >>"), text.index("<< labels >>")
    open(mag, "w").write(text[:i] + "<< metal1 >>\nrect 0 0 200 100\n" + text[j:])     # metal and labels only
    r = L.compare(d, L.pairs(d)[0])
    assert r["verdict"] == "layout has no devices" and L.finding(r) is None, r


def test_same_circuit_with_other_ports_is_a_note():
    r = dict(verdict="match, ports differ", cell="c", mag="c.mag", sch="c.sch",
             ports=["OE |(no matching pin)", "Circuit1 instance nfet:6 pin li_1# connections are no connects (1)"])
    f = L.finding(r)
    assert f["rule"] == "layout/ports_differ" and f["severity"] == "info" and "no connects" in f["title"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

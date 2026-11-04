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


def sch(model="nfet_01v8", w=1, l=0.4, body="VSUBS"):
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
C {{devices/lab_pin.sym}} 20 0 0 1 {{name=p4 lab={body}}}
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


IDEAL_REPORT = """Subcircuit summary:
Circuit 1: ring                            |Circuit 2: ring
-------------------------------------------|-------------------------------------------
sky130_fd_pr__nfet_01v8 (20)               |sky130_fd_pr__nfet_01v8 (20)
(no matching element)                      |10fF (18)
Number of devices: 40 **Mismatch**         |Number of devices: 58 **Mismatch**
"""


def test_ideal_schematic_parts_are_named_not_hidden():
    """A ring's schematic loads every stage with an ideal 10 fF capacitor (no PDK model, so nothing to draw): before,
    Netgen's failure was read as 'pins or nets only' and not judged (8 cells in 98 repos)."""
    d = L.differences(L.counts(IDEAL_REPORT))
    assert d == [dict(kind="ideal", model="10fF", n_layout=0, n_schematic=18)], d
    r = dict(verdict="ideal parts in schematic", cell="ring", mag="ring.mag", sch="ring.sch", diffs=d)
    f = L.finding(r)
    assert f["rule"] == "layout/ideal_parts" and f["severity"] == "info" and "18 x 10fF" in f["title"], f
    r = dict(r, verdict="devices differ", diffs=d + [dict(kind="count", model="sky130_fd_pr__pfet_01v8", n_layout=2,
                                                          n_schematic=1)])
    f = L.finding(r)
    assert f["rule"] == "layout/devices_differ" and "also simulates ideal parts (18 x 10fF)" in f["title"], f


def test_fixed_width_resistor_is_the_generic_model_at_that_width():
    t = L.generic_resistors("X0 a b vss sky130_fd_pr__res_high_po_0p69 l=20.35\n"
                            "XR3 c d vss sky130_fd_pr__res_xhigh_po_5p73 W=5.73 L=3\n"
                            "XR1 net1 in vss sky130_fd_pr__res_high_po W=0.690 L=20.35\n")
    assert t.splitlines() == ["X0 a b vss sky130_fd_pr__res_high_po l=20.35 w=0.69",
                              "XR3 c d vss sky130_fd_pr__res_xhigh_po W=5.73 L=3",
                              "XR1 net1 in vss sky130_fd_pr__res_high_po W=0.690 L=20.35"], t
    assert L.family("sky130_fd_pr__res_xhigh_po_1p41") == "sky130_fd_pr__res_xhigh_po"


def test_a_body_left_untied_is_found_by_tying_it():
    """The schematic ties the transistor's body to its source; the layout leaves it on the substrate net, which
    reaches nothing else. Tied as the schematic ties it, Netgen matches: the verdict says so instead of 'not judged'.
    Our fixture is a project's top cell, so it is a warning."""
    if not L.available():
        return
    d = _repo(body="S")
    r = L.compare(d, L.pairs(d)[0])
    assert r["verdict"] == "bodies untied", r
    assert r["bodies"] == [dict(net="VSUBS", devices=1, kind="nfet", tied_to="S")], r["bodies"]
    f = L.finding(r)
    assert f["rule"] == "layout/bodies_untied" and f["severity"] == "warn" and "1 nfet body on VSUBS" in f["title"], f


def test_tie_bodies_leaves_a_net_with_other_terminals():
    lay = (".subckt c vdd vss a y w1\nX0 y a vss vss sky130_fd_pr__nfet_01v8 w=1 l=0.15\n"
           "X1 y a vdd w1 sky130_fd_pr__pfet_01v8 w=1 l=0.15\nR0 w1 vdd sky130_fd_pr__res_generic_nd l=1\n.ends\n")
    sch = ".subckt c vdd vss a y\nXM0 y a vss vss sky130_fd_pr__nfet_01v8 W=1 L=0.15\nXM1 y a vdd vdd sky130_fd_pr__pfet_01v8 W=1 L=0.15\n.ends\n"
    assert L.tie_bodies(lay, sch) == (lay, [])          # w1 also reaches a resistor: not a body-only net
    t, how = L.tie_bodies(lay.replace("R0 w1 vdd sky130_fd_pr__res_generic_nd l=1\n", ""), sch)
    assert how == [dict(net="w1", devices=1, kind="pfet", tied_to="vdd")] and ".subckt c vdd vss a y\n" in t, (t, how)


def test_split_pin_pieces_joined():
    lay = ".subckt buf A Y VDD VSS VDD_uq1\nX0 Y A VDD VDD sky130_fd_pr__pfet_01v8 w=1 l=0.15\nX1 Y A VDD_uq1 VDD_uq1 sky130_fd_pr__pfet_01v8 w=1 l=0.15\n.ends\n"
    t = L.join_split(lay, L.split_nets(lay))
    assert t.splitlines()[0] == ".subckt buf A Y VDD VSS" and "VDD_uq1" not in t, t
    r = dict(cell="buf", mag="buf.mag", sch="buf.sch", split={"VDD": 2}, verdict="split pins only")
    f = L.split_finding(r)
    assert f["severity"] == "info" and "Netgen matches the schematic: nothing else differs" in f["title"], f
    assert "nothing else differs" not in L.split_finding(dict(r, verdict="pins or nets only"))["title"]

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


SPLIT = """.subckt buffer in out vdd vdd_uq0 vdd_uq1 vss
X0 out in vss vss sky130_fd_pr__nfet_01v8 w=1 l=0.15
X1 out in vdd vdd sky130_fd_pr__pfet_01v8 w=2 l=0.15
X2 out in vdd_uq0 vdd_uq0 sky130_fd_pr__pfet_01v8 w=2 l=0.15
.ends
"""


def test_a_pin_in_pieces_is_split():
    assert L.split_nets(SPLIT) == {"vdd": 3}
    assert L.split_nets(SPLIT.replace(" vdd_uq0 vdd_uq1", "")) == {}
    r = dict(cell="buffer", mag="mag/buffer.mag", split={"vdd": 3})
    f = L.split_finding(r)
    assert f["rule"] == "layout/split_pin" and f["severity"] == "info" and "vdd in 3 pieces" in f["title"]
    g = L.split_finding(dict(r, cell="tt_um_kaaval_buffer"))            # the project's top cell: nothing above joins them
    assert g["severity"] == "warn" and "only the piece" in g["title"]
    assert L.split_finding(dict(r, split={})) is None


def test_global_labels_are_one_net_in_the_flat_schematic():
    """A sub-cell powered by a vdd.sym label (global=true): its VDD is the top's VDD in the flat schematic the layout
    is compared with, not a separate x1/VDD (a ring of such stages read as 'pins or nets only', 2 Nov)."""
    d = tempfile.mkdtemp()
    head = "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
    sym = ("v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {type=subcircuit\nformat=\"@name @pinlist @symname\"\n"
           "template=\"name=x1\"\n}\nV {}\nS {}\nE {}\nB 5 -2.5 -2.5 2.5 2.5 {name=mid dir=out}\n")
    open(os.path.join(d, "div.sym"), "w").write(sym)
    open(os.path.join(d, "div.sch"), "w").write(head +
        "C {devices/res.sym} 0 0 0 0 {name=R1 value=1k}\nC {devices/vdd.sym} 0 -30 0 0 {name=l1 lab=VDD}\n"
        "C {devices/lab_pin.sym} 0 30 0 0 {name=p1 lab=mid}\nC {devices/opin.sym} 100 0 0 0 {name=p3 lab=mid}\n")
    open(os.path.join(d, "top.sym"), "w").write(sym.replace("name=mid dir=out", "name=out dir=out"))
    open(os.path.join(d, "top.sch"), "w").write(head +
        "C {div.sym} 0 0 0 0 {name=x1}\nC {devices/lab_pin.sym} 0 0 0 0 {name=p1 lab=out}\n"
        "C {div.sym} 0 100 0 0 {name=x2}\nC {devices/lab_pin.sym} 0 100 0 0 {name=p2 lab=out}\n"
        "C {devices/opin.sym} 100 0 0 0 {name=p3 lab=out}\n")
    flat = L.schematic_subckt(d, dict(cell="top", sch="top.sch", sym="top.sym", mag=""))
    res = [l.split() for l in flat.splitlines() if l.split() and l.split()[0].lower().endswith("r1")]
    assert len(res) == 2 and all("VDD" in r for r in res) and "x1/VDD" not in flat, flat


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_strip_ideal_keeps_pdk_parts():
    from kaaval_engine import layout_check as LC
    t = ("XM1 d g s b sky130_fd_pr__nfet_01v8 W=1 L=1\nR1 a b 2k\n+ m=1\nC1 a 0 1p\nI1 vdd vb 20u\n"
         "XR2 a b sky130_fd_pr__res_xhigh_po_0p35 L=10\nR3 a b sky130_fd_pr__res_generic_po W=1 L=1\n")
    assert LC.strip_ideal(t) == ("XM1 d g s b sky130_fd_pr__nfet_01v8 W=1 L=1\nXR2 a b sky130_fd_pr__res_xhigh_po_0p35 L=10\n"
                                 "R3 a b sky130_fd_pr__res_generic_po W=1 L=1\n")


def test_sizes_found_beside_ideal_parts():
    """The demo tile's kv_amp layout draws M8 12 um wide (16 in the schematic) and its schematic has an ideal R, C and
    current source: Netgen stops at those, so the sizes were never compared and the note said they were the same."""
    from kaaval_engine import layout_check as LC
    if not LC.available():
        print("skip: Magic / Netgen not installed")
        return
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "demo_tapeout")
    res, fs, _ = LC.review(root)
    by = {r["cell"]: r for r in res}
    assert by["kv_amp"]["verdict"] == "sizes differ" and by["kv_amp"]["sizes"] == ["M8: w 12 in the layout, 16 in the schematic"]
    assert by["kv_ref"]["verdict"] == "ideal parts in schematic"

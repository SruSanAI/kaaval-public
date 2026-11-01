"""SPICE subcircuits as review cells: only definitions are kept, nothing executable from the file survives."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import spice_cells

TEXT = """* a repository netlist
.include /etc/passwd
.lib "evil.lib" tt
.subckt amp vdd vss in out
XM1 out in vss vss sky130_fd_pr__nfet_01v8 L=1 W=2
.include inner.spice
R1 vdd out 10k
.ends amp
.control
shell rm -rf /
.endc
.tran 1n 1u
"""


def test_only_definitions_survive():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "a.spice"), "w").write(TEXT)
    cells = spice_cells.find_cells(d)
    assert [c["cell"] for c in cells] == ["a.spice#amp"] and cells[0]["ports"] == ["vdd", "vss", "in", "out"]
    circ, ports = spice_cells.load(d, "a.spice#amp")
    low = circ.lower()
    assert ".include" not in low and ".lib" not in low and "shell" not in low and ".tran" not in low and ".control" not in low
    assert circ.splitlines()[-1] == "Xdut vdd vss in out amp"


def test_ports_continued_on_plus_lines():
    """Magic writes ten pins to a line: a Tiny Tapeout top cell's VPWR / VGND come on the third line. Before (2 Nov),
    only the first line counted: 757 of 4118 SPICE cells in the 98 clones had a truncated port list, 269 of them
    lost their supply or ground pin and were never powered up."""
    d = tempfile.mkdtemp()
    open(os.path.join(d, "t.spice"), "w").write(
        ".subckt top clk ena rst_n ua[0] ua[1]\n+ ui_in[0] ui_in[1]\n+ VPWR VGND\nXc VGND ua[1] VPWR ua[0] comp\n.ends\n"
        ".subckt comp vss inp vdd out W=1\nR1 vdd out 1k\n.ends\n"
        ".subckt p a b\n+ c PARAMS: w=1\n+ l=2\nR1 a b 1k\n.ends\n")
    cells = {c["cell"]: c["ports"] for c in spice_cells.find_cells(d)}
    assert cells["t.spice#top"] == ["clk", "ena", "rst_n", "ua[0]", "ua[1]", "ui_in[0]", "ui_in[1]", "VPWR", "VGND"]
    assert cells["t.spice#comp"] == ["vss", "inp", "vdd", "out"] and cells["t.spice#p"] == ["a", "b", "c"], cells
    circ, ports = spice_cells.load(d, "t.spice#top")
    assert circ.splitlines()[-1] == "Xdut " + " ".join(ports) + " top"
    from kaaval_engine import plan as P
    plan = dict(cell="t.spice#top", kind="powerup", supplies={"VPWR": 1.8}, grounds=["VGND"])
    assert "ua[0]" not in P.undriven(plan, d) and "clk" in P.undriven(plan, d)   # ua[0] reaches comp's resistor


def test_cell_outside_the_root_is_refused():
    d = tempfile.mkdtemp()
    assert spice_cells.load(d, "../../etc/hosts#x") == (None, None)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

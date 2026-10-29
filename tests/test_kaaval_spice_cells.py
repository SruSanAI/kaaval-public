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


def test_cell_outside_the_root_is_refused():
    d = tempfile.mkdtemp()
    assert spice_cells.load(d, "../../etc/hosts#x") == (None, None)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

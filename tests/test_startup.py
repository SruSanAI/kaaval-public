"""app/startup.py: Muse Spark's start-up devices become SPICE lines on the cell's nets, bad ones are refused with a
reason, and the cell is rewritten as its own subcircuit with them. No model, no simulation."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import startup  # noqa: E402


def test_lines_and_refusals():
    devs = [dict(name="MS1", type="nfet", d="n2", g="kick", s="vss", b="vss", W=1, L=0.5, value=""),
            dict(name="RS1", type="res", d="vdd", s="kick", g="", b="", W=0, L=0, value="200k"),
            dict(name="M1", type="pfet", d="a", g="b", s="vdd", b="vdd", W=1, L=1, value=""),        # name taken
            dict(name="MS2", type="nfet", d="n 1", g="x", s="vss", b="vss", W=1, L=1, value=""),     # bad net
            dict(name="MS3", type="nfet", d="a", g="x", s="vss", b="vss", W=400, L=1, value="")]     # too wide
    out, errors = startup.lines(devs, {"devices": {"M1", "XM1"}}, ["vdd", "vss", "iout"])
    assert out == ["XMS1 n2 kick vss vss sky130_fd_pr__nfet_01v8 W=1 L=0.5 nf=1", "RRS1 vdd kick 200k"], out
    assert len(errors) == 3 and "already used" in errors[0] and "net name" in errors[1] and "outside" in errors[2], errors


def test_cell_text_is_its_own_subcircuit():
    rec = {"cell": "xschem/kv_ref.sch", "ports": ["vdd", "vss", "iout"], "netlist": "XM1 n1 n1 vss vss sky130_fd_pr__nfet_01v8 W=4 L=2\n"}
    t = startup.cell_text(rec, "kv_ref_startup", ["RRS1 vdd kick 200k"])
    assert ".subckt kv_ref_startup vdd vss iout\nXM1 n1 n1 vss vss" in t and "RRS1 vdd kick 200k\n.ends kv_ref_startup" in t


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

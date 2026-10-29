"""Standard cells a design instantiates are simulated from the PDK's own transistor-level definitions."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import sim, stdcells

INV = """V1 vdd 0 1.8
Vin a 0 0
Xinv a 0 0 vdd vdd y sky130_fd_sc_hd__inv_1
Xbuf y 0 0 vdd vdd z sky130_fd_sc_hd__buf_1"""


def test_only_used_cells_are_added():
    d = stdcells.defs_for(INV)
    assert d.lower().count(".subckt") == 2 and "sky130_fd_sc_hd__inv_1" in d and "pfet_01v8_hvt" in d
    assert stdcells.defs_for(INV + "\n.subckt sky130_fd_sc_hd__inv_1 A VGND VNB VPB VPWR Y\n.ends").lower().count(".subckt") == 1


def test_inverter_chain_simulates():
    tb = sim.Testbench(sch="own.sch", circuit=INV, analyses=[".op"])
    out, err = sim.run(sim.deck(tb, control="op\nprint v(y) v(z)"))
    assert not err, err
    vy = float(out.split("v(y) =")[1].split()[0]); vz = float(out.split("v(z) =")[1].split()[0])
    assert vy > 1.7 and vz > 1.7, (vy, vz)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

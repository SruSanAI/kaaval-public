"""The no-model baseline's choice of cells: a block built only from standard cells is digital and gets no analog
power-up test; one transistor of its own, or a sub-circuit of the project's own, keeps it analog."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.planner import digital_only

SAR = """x2 c9 VSS VCC reset_in VSS VSS VCC VCC net1 q_n9 sky130_fd_sc_hd__dfbbp_1
x3 net1 VSS VSS VCC VCC net2 sky130_fd_sc_hd__buf_1"""


def test_standard_cells_only_is_digital():
    assert digital_only(SAR)


def test_a_transistor_or_own_subcircuit_keeps_it_analog():
    assert not digital_only(SAR + "\nXM1 out in VSS VSS sky130_fd_pr__nfet_01v8 L=0.15 W=1")
    assert not digital_only(SAR + "\nx9 a b VCC VSS my_switch")
    assert not digital_only("")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

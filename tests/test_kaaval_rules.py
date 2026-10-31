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

def test_rail_guess_keeps_1v8_parts_at_1v8():
    from app.planner import rail_volts
    mixed = ("XB1 out in VDD VDD sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=1\n"
             "XE1 a b VSS VSS VDD VDD y sky130_fd_sc_hd__nand2_1\n")
    v, why = rail_volts("VDD", mixed)                       # thick buffer + hd encoder on one rail: 1.8 V
    assert v == 1.8 and "XE1" in why and "XB1" in why, why
    assert rail_volts("VDD", mixed.splitlines()[0])[0] == 3.3            # thick-oxide only: 3.3 V
    assert rail_volts("VAPWR", mixed.replace("VDD", "VAPWR"))[0] == 3.3  # the 3.3 V pin by name, whatever is on it
    assert rail_volts("VDD", "XN1 o i VSS VSS sky130_fd_pr__nfet_01v8 L=0.15 W=1")[0] == 1.8


def test_chip_without_vapwr_powers_every_block_at_1v8():
    import tempfile
    from app import runner
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "src"))
        open(os.path.join(d, "src", "project.v"), "w").write(
            "module top_x (input wire VGND, input wire VPWR, input wire [7:0] ui_in, inout wire [7:0] ua);\nendmodule\n")
        assert runner.NO_3V3 in runner.chip_supplies(d)
        open(os.path.join(d, "src", "project.v"), "w").write(
            "module top_x (input wire VGND, input wire VDPWR, input wire VAPWR, inout wire [7:0] ua);\nendmodule\n")
        assert runner.chip_supplies(d) == ""                                  # a 3.3 V pin exists: no override
    assert runner.chip_supplies(tempfile.gettempdir() + "/nonexistent") == ""


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


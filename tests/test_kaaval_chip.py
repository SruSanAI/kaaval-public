"""The whole-tile reader (kaaval_engine.chip) on a small Tiny Tapeout project of our own: rails, pads and blocks are
read from src/*.v and info.yaml as text; each pin is classified by what it reaches; blocks with a schematic of the same
name are analog, modules of src/ are digital; a synthesized netlist elsewhere in src/ is not taken for the design."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import chip

INFO = """project:
  top_module:  "tt_um_kaaval_demo"
  analog_pins: 2
  uses_3v3: true
pinout:
  ua[0]: "vref"
  ua[1]: "vout"
"""
SRC = """`default_nettype none
module tt_um_kaaval_demo (input wire VGND, input wire VDPWR, input wire VAPWR, input wire [7:0] ui_in,
    output wire [7:0] uo_out, inout wire [7:0] ua, input wire clk, input wire rst_n, input wire ena);
  wire en_a; wire cmp;
  ctrl u_ctrl (.clk(clk), .rst_n(rst_n), .start(ui_in[0]), .en(en_a), .cmp(cmp), .done(uo_out[0]));
  ref_amp u_amp (.AVDD(VAPWR), .VDD(VDPWR), .VSS(VGND), .EN(en_a), .VREF(ua[0]), .VOUT(ua[1]), .CMP(cmp));
endmodule
module ctrl (input clk, input rst_n, input start, output reg en, input cmp, output done);
  // a comment with u_fake (.x(y)) inside
  assign done = cmp;
endmodule
"""
GATES = "module netlist_only (input a, output y);\n  sky130_fd_sc_hd__inv_1 g1 (.A(a), .Y(y));\nendmodule\n"


def test_tile_of_a_small_mixed_signal_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "xschem").mkdir()
    (tmp_path / "info.yaml").write_text(INFO)
    (tmp_path / "src" / "project.v").write_text(SRC)
    (tmp_path / "src" / "gl.v").write_text(GATES)
    (tmp_path / "xschem" / "ref_amp.sch").write_text("v {xschem version=3.4.5 file_version=1.2}\n")
    t = chip.read(str(tmp_path))
    assert t["top"] == "tt_um_kaaval_demo" and t["uses_3v3"] and t["analog_pins"] == 2
    assert t["rails"] == ["VAPWR", "VDPWR", "VGND"] and t["analog_pads"] == ["ua[0]", "ua[1]"]
    by = {i["name"]: i for i in t["instances"]}
    assert set(by) == {"u_ctrl", "u_amp"}                         # the gate netlist is not the tile
    amp, ctl = by["u_amp"], by["u_ctrl"]
    assert amp["analog"] and amp["cell"] == os.path.join("xschem", "ref_amp.sch") and ctl["digital"]
    k = {p["port"]: p for p in amp["pins"]}
    assert k["AVDD"]["kind"] == "rail" and k["AVDD"]["volts"] == 3.3 and k["VREF"]["pad"] == "ua[0]"
    assert k["EN"]["kind"] == "internal" and k["CMP"]["kind"] == "internal"
    c = {p["port"]: p for p in ctl["pins"]}
    assert c["clk"]["kind"] == "clock" and c["start"]["kind"] == "digital_in" and c["done"]["kind"] == "digital_out"


if __name__ == "__main__":
    import pathlib, tempfile
    test_tile_of_a_small_mixed_signal_project(pathlib.Path(tempfile.mkdtemp()))
    print("ok test_tile_of_a_small_mixed_signal_project")

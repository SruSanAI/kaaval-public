"""make_demo_mixed.py — examples/demo_mixed: a second Tiny Tapeout-shaped analog tile of our own, with a 3.3 V rail, for
the checks the first demo tile has no flaw for. Every block has a flaw on purpose:
  kv_osc   a current-starved ring oscillator (wired xschem schematic, transient testbench tb_osc.sch) whose starving
           bias comes from a resistive divider near threshold: at slow, cold, low-supply corners it stops switching;
  kv_xref  a 1.8 V beta-multiplier reference whose only start-up is a capacitor kick from the 3.3 V rail (the circuit of
           tests/test_kaaval_sequence.py): if the 3.3 V rail comes up first, it wakes up dead;
  kv_cross a 3.3 V inverter driving 1.8 V transistors directly, no level shifter (tests/test_kaaval_domains.py, A):
           the thin-oxide devices see 3.3 V;
  kv_vref  a 0.9 V reference from a 100k / 100k divider (tests/test_kaaval_drive.py): too weak for the pad.

    python tools/make_demo_mixed.py         # writes examples/demo_mixed/
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_demo_tapeout import Sheet, N, P, SYM  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "examples", "demo_mixed")
STAGES = 5
PITCH = 200
R_TOP, R_BOT = "200k", "100k"


def osc():
    """kv_osc.sch: five current-starved inverters in a ring, ports vdd, vss, osc; the starving NMOS gates sit on a
    200k / 100k divider (0.6 V at 1.8 V): near threshold on purpose."""
    s = Sheet()
    xl = (STAGES - 1) * PITCH
    s.pin(-320, -80, "vdd"); s.pin(-320, 380, "vss"); s.pin(xl + 160, 75, "osc")
    s.wire((-320, -80), (xl + 40, -80), net="vdd")
    s.wire((-320, 380), (xl + 40, 380), net="vss")
    s.dev("res", "R1", -260, 60, R_TOP); s.dev("res", "R2", -260, 300, R_BOT)
    s.wire((-260, -80), (-260, 30), net="vdd"); s.wire((-260, 90), (-260, 270), net="vbn"); s.wire((-260, 330), (-260, 380), net="vss")
    s.wire((-260, 200), (xl - 20, 200), net="vbn")
    for i in range(STAGES):
        x = i * PITCH
        s.mos(P, f"MP{i + 1}", x, 0, "vdd", 2, 0.5)
        s.mos(N, f"MN{i + 1}", x, 150, "vss", 1, 0.5)
        s.mos(N, f"MS{i + 1}", x, 300, "vss", 1, 2)
        s.wire((x + 20, -80), (x + 20, -30), net="vdd")
        s.wire((x - 20, 0), (x - 20, 150), net=f"s{i}")                       # the stage's input: both gates
        s.wire((x + 20, 30), (x + 20, 120), net=f"s{i + 1}")                   # its output: both drains
        s.wire((x + 20, 180), (x + 20, 270), net=f"t{i + 1}")                  # NMOS source to its starving device
        s.wire((x + 20, 330), (x + 20, 380), net="vss")
        s.wire((x - 20, 200), (x - 20, 300), net="vbn")                        # starving gate from the bias bus
        if i < STAGES - 1:
            s.wire((x + 20, 75), (x + PITCH - 20, 75), net=f"s{i + 1}")        # into the next stage's gates
    s.wire((xl + 20, 75), (xl + 60, 75), net="osc"); s.wire((xl + 60, 75), (xl + 160, 75), net="osc")
    s.wire((xl + 60, 75), (xl + 60, 440), (-60, 440), (-60, 75), (-20, 75), net="osc")   # the ring closes
    s.lab(-260, 150, "vbn")
    return s.text()


def osc_testbench():
    """tb_osc.sch: 1.8 V, the ring, 20 fF on its output; a 4 us transient."""
    s = Sheet()
    s.dev("vsource", "V1", -200, 0, 1.8)
    s.lines.append("C {kv_osc.sym} 100 0 0 0 {name=x1}")
    s.dev("capa", "C1", 300, 60, "20f")
    s.wire((-200, -30), (-200, -120), (100, -120), (100, -60), net="vdd")
    s.wire((180, 0), (300, 0), (300, 30), net="osc")
    s.wire((-200, 160), (300, 160), net="0")
    for x, y in ((-200, 30), (100, 60), (300, 90)):
        s.wire((x, y), (x, 160), net="0")
    s.lab(-200, -120, "vdd"); s.lab(300, 0, "osc", flip=1); s.lab(-200, 160, "0")
    s.lines.append("C {sky130_fd_pr/corner.sym} -200 -300 0 0 {name=CORNER only_toplevel=true corner=tt}")
    s.lines.append('C {devices/code_shown.sym} -200 260 0 0 {name=s1 only_toplevel=false value=".tran 2n 4u\n.save all"}')
    return s.text()


XREF = """* kv_xref: a 1.8 V beta-multiplier reference; its only start-up is a 200 fF kick from the 3.3 V rail (on purpose)
.subckt kv_xref vdd avdd vss iout
XM1 n1 n1 vss vss sky130_fd_pr__nfet_01v8 L=2 W=4 nf=1 m=1
XM2 n2 n1 s2 vss sky130_fd_pr__nfet_01v8 L=2 W=16 nf=1 m=1
R1 s2 vss 20k
XM3 n1 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM4 n2 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM5 iout n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
Ckick avdd n1 200f
.ends kv_xref
"""
CROSS = """* kv_cross: a 3.3 V inverter (thick-oxide) drives a 1.8 V inverter's gates directly, no level shifter (on purpose)
.subckt kv_cross vdd avdd vss in out
XH1 mid in avdd avdd sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=1 nf=1 m=1
XH2 mid in vss vss sky130_fd_pr__nfet_g5v0d10v5 L=0.5 W=1 nf=1 m=1
XL1 out mid vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1
XL2 out mid vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
.ends kv_cross
"""
VREF = """* kv_vref: a 0.9 V reference from a 100k / 100k divider, straight to its pad (on purpose: 50 kOhm output resistance)
.subckt kv_vref vdd vss vref
R1 vdd vref 100k
R2 vref vss 100k
.ends kv_vref
"""

VERILOG = """`default_nettype none
// Kaaval mixed-domain demo tile: four analog blocks, two rails (1.8 V VDPWR, 3.3 V VAPWR).
module tt_um_kaaval_mixed (
    input  wire       VGND,
    input  wire       VDPWR,
    input  wire       VAPWR,
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    inout  wire [7:0] ua,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  assign uo_out = 8'b0;
  assign uio_out = 8'b0;
  assign uio_oe = 8'b0;
  kv_osc   o0 (.vdd(VDPWR), .vss(VGND), .osc(ua[0]));
  kv_xref  x0 (.vdd(VDPWR), .avdd(VAPWR), .vss(VGND), .iout(ua[1]));
  kv_cross c0 (.vdd(VDPWR), .avdd(VAPWR), .vss(VGND), .in(ua[2]), .out(ua[3]));
  kv_vref  v0 (.vdd(VDPWR), .vss(VGND), .vref(ua[4]));
endmodule
"""

INFO = """# Kaaval mixed-domain demo tile (ours): a Tiny Tapeout-shaped analog project, never submitted to a shuttle.
project:
  title: "Kaaval demo 2: two rails, four blocks"
  author: "Sanjay Sivakumar"
  description: "An oscillator, a cross-domain reference, a 3.3 V to 1.8 V interface and a pad reference, each with a flaw on purpose."
  language: "Analog"
  tiles: "1x2"
  analog_pins: 5
  uses_3v3: true
  top_module: "tt_um_kaaval_mixed"
pinout:
  ua[0]: "osc: ring oscillator output"
  ua[1]: "iout: reference current (1.8 V core, start-up kick from 3.3 V)"
  ua[2]: "in: 3.3 V logic input"
  ua[3]: "out: 1.8 V logic output"
  ua[4]: "vref: 0.9 V reference"
"""

README = """# Kaaval demo tile 2: two rails

A second Tiny Tapeout-shaped analog project **of our own** (written by `tools/make_demo_mixed.py`), with both the 1.8 V
(VDPWR) and the 3.3 V (VAPWR) rail. Every block has a flaw **on purpose**; review it by uploading a zip of this folder.

| Block | What it is | Planted flaw |
|---|---|---|
| `xschem/kv_osc.sch` | a five-stage current-starved ring oscillator (`tb_osc.sch`: 1.8 V, 20 fF, 4 us transient) | its starving bias is a 200k / 100k divider, 0.6 V: near threshold |
| `spice/kv_xref.spice` | a 1.8 V beta-multiplier current reference | its only start-up is a 200 fF kick from the 3.3 V rail |
| `spice/kv_cross.spice` | a 3.3 V inverter driving a 1.8 V inverter | no level shifter: 1.8 V thin-oxide gates see the 3.3 V swing |
| `spice/kv_vref.spice` | a 0.9 V reference to its pad | a 100k / 100k divider: 50 kOhm output resistance |

Never submitted to a shuttle.
"""


def main():
    osym = SYM.replace("name=iout", "name=osc").replace("name=x1", "name=x1")
    files = {"xschem/kv_osc.sch": osc(), "xschem/kv_osc.sym": osym, "xschem/tb_osc.sch": osc_testbench(),
             "spice/kv_xref.spice": XREF, "spice/kv_cross.spice": CROSS, "spice/kv_vref.spice": VREF,
             "src/project.v": VERILOG, "info.yaml": INFO, "README.md": README}
    for rel, text in files.items():
        p = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

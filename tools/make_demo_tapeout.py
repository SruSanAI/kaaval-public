"""make_demo_tapeout.py — examples/demo_tapeout: a Tiny Tapeout-shaped analog project of our own, for demos and the video.

Its block is the beta-multiplier current reference of tests/test_kaaval_startup.py (BETA), drawn as xschem schematics,
deliberately WITHOUT a start-up device: a review must find that it can power up dead. The files are written here so
they stay reproducible; xschem netlists them to the same devices as BETA (check: xschem -n -q -x xschem/tb_ref.sch).

    python tools/make_demo_tapeout.py            # writes examples/demo_tapeout/
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "examples", "demo_tapeout")
N, P = "sky130_fd_pr/nfet_01v8.sym", "sky130_fd_pr/pfet_01v8.sym"
NPIN = {"D": (20, -30), "G": (-20, 0), "S": (20, 30), "B": (20, 0)}
PPIN = {"D": (20, 30), "G": (-20, 0), "S": (20, -30), "B": (20, 0)}
HEAD = ["v {xschem version=3.4.5 file_version=1.2}", "G {}", "K {}", "V {}", "S {}", "E {}"]


class Sheet:
    def __init__(self):
        self.lines, self.n = list(HEAD), 0

    def lab(self, x, y, net, flip=0):
        self.n += 1
        if net == "0":
            self.lines.append(f"C {{devices/gnd.sym}} {x} {y} 0 0 {{name=l{self.n} lab=GND}}")
        else:
            self.lines.append(f"C {{devices/lab_pin.sym}} {x} {y} 0 {flip} {{name=p{self.n} lab={net}}}")

    def fet(self, sym, name, x, y, d, g, s, b, W, L):
        model = "nfet_01v8" if sym == N else "pfet_01v8"
        self.lines.append(f"C {{{sym}}} {x} {y} 0 0 {{name={name}\nW={W}\nL={L}\nnf=1\nmult=1\nmodel={model}\n"
                          f"spiceprefix=X\n}}")
        for pin, net in zip("DGSB", (d, g, s, b)):
            px, py = (NPIN if sym == N else PPIN)[pin]
            self.lab(x + px, y + py, net, flip=int(pin != "G"))

    def two(self, sym, name, x, y, p, m, value):
        self.lines.append(f"C {{devices/{sym}.sym}} {x} {y} 0 0 {{name={name} value={value}}}")
        self.lab(x, y - 30, p)
        self.lab(x, y + 30, m)

    def pin(self, x, y, net):
        self.n += 1
        self.lines.append(f"C {{devices/iopin.sym}} {x} {y} 0 0 {{name=p{self.n} lab={net}}}")

    def text(self):
        return "\n".join(self.lines) + "\n"


def block():
    """kv_ref.sch: the reference alone, ports vdd, vss, iout. No start-up device (on purpose)."""
    s = Sheet()
    for i, net in enumerate(("vdd", "vss", "iout")):
        s.pin(-300, -100 + 40 * i, net)
    s.fet(N, "M1", 0, 200, "n1", "n1", "vss", "vss", 4, 2)
    s.fet(N, "M2", 200, 200, "n2", "n1", "s2", "vss", 16, 2)
    s.two("res", "R1", 220, 320, "s2", "vss", "20k")
    s.fet(P, "M3", 0, 0, "n1", "n2", "vdd", "vdd", 8, 2)
    s.fet(P, "M4", 200, 0, "n2", "n2", "vdd", "vdd", 8, 2)
    s.fet(P, "M5", 400, 0, "iout", "n2", "vdd", "vdd", 8, 2)
    return s.text()


SYM = """v {xschem version=3.4.5 file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
E {}
L 4 -60 -40 60 -40 {}
L 4 60 -40 60 40 {}
L 4 60 40 -60 40 {}
L 4 -60 40 -60 -40 {}
L 7 0 -60 0 -40 {}
L 7 0 40 0 60 {}
L 7 60 0 80 0 {}
B 5 -2.5 -62.5 2.5 -57.5 {name=vdd dir=inout}
B 5 -2.5 57.5 2.5 62.5 {name=vss dir=inout}
B 5 77.5 -2.5 82.5 2.5 {name=iout dir=inout}
T {@symname} -40 -10 0 0 0.3 0.3 {}
T {@name} 10 -70 0 0 0.2 0.2 {}
"""


def testbench():
    """tb_ref.sch: 1.8 V supply, the reference, a 50 kOhm load on its output; the operating point."""
    s = Sheet()
    s.two("vsource", "V1", -200, 0, "vdd", "0", 1.8)
    s.lines.append("C {kv_ref.sym} 100 0 0 0 {name=x1}")
    s.lab(100, -60, "vdd")
    s.lab(100, 60, "0")
    s.lab(180, 0, "iout", flip=1)
    s.two("res", "R2", 300, 60, "iout", "0", "50k")
    s.lines.append("C {sky130_fd_pr/corner.sym} -200 -200 0 0 {name=CORNER only_toplevel=true corner=tt}")
    s.lines.append('C {devices/code_shown.sym} -200 200 0 0 {name=s1 only_toplevel=false value=".op\n.save all"}')
    return s.text()


VERILOG = """`default_nettype none
// Kaaval demo tile: one analog block, the current reference (xschem/kv_ref.sch), output on ua[0].
module tt_um_kaaval_demo (
    input  wire       VGND,
    input  wire       VDPWR,
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
  kv_ref r0 (.vdd(VDPWR), .vss(VGND), .iout(ua[0]));
endmodule
"""

INFO = """# Kaaval demo tile (ours): a Tiny Tapeout-shaped analog project, never submitted to a shuttle.
project:
  title: "Kaaval demo: current reference"
  author: "Sanjay Sivakumar"
  description: "A beta-multiplier current reference with no start-up device, on purpose: Kaaval's demo design."
  language: "Analog"
  tiles: "1x2"
  analog_pins: 1
  uses_3v3: false
  top_module: "tt_um_kaaval_demo"
pinout:
  ua[0]: "iout: reference current into the load"
"""

README = """# Kaaval demo tile

A Tiny Tapeout-shaped analog project **of our own**, made for Kaaval's demos (written by `tools/make_demo_tapeout.py`).
Its one block, `xschem/kv_ref.sch`, is a self-biased (beta-multiplier) current reference **without a start-up device, on
purpose**: DC analysis finds its working bias, but powered up from 0 V it can stay at zero current. Kaaval's README
reports this reference staying at 0 uA at 30 of 45 conditions. Review it: upload a zip of this folder.

`xschem/tb_ref.sch` is its testbench (1.8 V, a 50 kOhm load, operating point). Never submitted to a shuttle.
"""


def main():
    files = {"xschem/kv_ref.sch": block(), "xschem/kv_ref.sym": SYM, "xschem/tb_ref.sch": testbench(),
             "src/project.v": VERILOG, "info.yaml": INFO, "README.md": README}
    for rel, text in files.items():
        p = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

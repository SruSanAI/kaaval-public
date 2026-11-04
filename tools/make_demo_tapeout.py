"""make_demo_tapeout.py — examples/demo_tapeout: a Tiny Tapeout-shaped analog project of our own, for demos and the video.
Schematics drawn with wires; kv_ref and kv_amp also drawn as sky130 layouts with Magic (mag/), and the tile with both.

Three blocks, each with a flaw on purpose, drawn as xschem schematics:
  kv_ref  the beta-multiplier current reference of tests/test_kaaval_startup.py (BETA) WITHOUT a start-up device: a
          review must find that it can power up dead;
  kv_amp  the two-stage Miller op-amp of tests/test_kaaval_stability.py with a 0.5 pF compensation capacitor, in a
          unity follower driving 10 pF (tb_amp.sch): a review must find its thin phase margin from that testbench;
          its layout draws M8 12 um wide where the schematic says 16: layout against schematic must find it;
  kv_bias a resistor-set mirror sized SI-style (W=2u L=1u): the units audit must find that sky130 reads 2e-6 um. The files are written here so
they stay reproducible; xschem netlists them to the same devices as BETA (check: xschem -n -q -x xschem/tb_ref.sch).

    python tools/make_demo_tapeout.py            # writes examples/demo_tapeout/
"""
import os, re

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

    def wire(self, *pts, net=""):
        """A drawn wire through pts (one N line per segment)."""
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            self.lines.append(f"N {x1} {y1} {x2} {y2} {{lab={net}}}")

    def mos(self, sym, name, x, y, b, W, L):
        """A transistor whose drain, gate and source are wired by the caller; only its body is a label (the usual
        way to draw a body tie). Pins: D/S at x+20, y-/+30 (swapped for pfet), G at x-20, y."""
        model = "nfet_01v8" if sym == N else "pfet_01v8"
        self.lines.append(f"C {{{sym}}} {x} {y} 0 0 {{name={name}\nW={W}\nL={L}\nnf=1\nmult=1\nmodel={model}\n"
                          f"spiceprefix=X\n}}")
        self.lab(x + 20, y, b, flip=1)

    def dev(self, sym, name, x, y, value):
        """A two-pin part, pins at (x, y-30) and (x, y+30), wired by the caller."""
        self.lines.append(f"C {{devices/{sym}.sym}} {x} {y} 0 0 {{name={name} value={value}}}")

    def pin(self, x, y, net):
        self.n += 1
        self.lines.append(f"C {{devices/iopin.sym}} {x} {y} 0 0 {{name=p{self.n} lab={net}}}")

    def text(self):
        return "\n".join(self.lines) + "\n"


def block():
    """kv_ref.sch: the reference alone, ports vdd, vss, iout, drawn with wires. No start-up device (on purpose)."""
    s = Sheet()
    s.pin(-300, -100, "vdd"); s.pin(-300, 400, "vss"); s.pin(560, 100, "iout")
    s.mos(P, "M3", 0, 0, "vdd", 8, 2); s.mos(P, "M4", 200, 0, "vdd", 8, 2); s.mos(P, "M5", 400, 0, "vdd", 8, 2)
    s.mos(N, "M1", 0, 200, "vss", 4, 2); s.mos(N, "M2", 200, 200, "vss", 16, 2)
    s.dev("res", "R1", 220, 300, "20k")
    s.wire((-300, -100), (420, -100), net="vdd")                                  # supply rail and drops
    for x in (20, 220, 420):
        s.wire((x, -100), (x, -30), net="vdd")
    s.wire((-300, 400), (220, 400), net="vss")
    s.wire((20, 230), (20, 400), net="vss"); s.wire((220, 330), (220, 400), net="vss")
    s.wire((220, 230), (220, 270), net="s2")                                     # M2 source into R1
    s.wire((20, 30), (20, 170), net="n1")                                        # M3 drain = M1 drain, gates of M1, M2
    s.wire((-20, 200), (-40, 200), (-40, 120), (20, 120), net="n1")
    s.wire((180, 200), (160, 200), (160, 120), (20, 120), net="n1")
    s.wire((220, 30), (220, 170), net="n2")                                      # M4 diode = M2 drain, gates of M3-M5
    s.wire((180, 0), (160, 0), (160, 60), (220, 60), net="n2")
    s.wire((-20, 0), (-40, 0), (-40, -60), (160, -60), (160, 0), net="n2")
    s.wire((380, 0), (360, 0), (360, 60), (220, 60), net="n2")
    s.wire((420, 30), (420, 100), (560, 100), net="iout")
    s.lab(-40, 120, "n1"); s.lab(360, 60, "n2", flip=1); s.lab(220, 250, "s2", flip=1)
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
    s.dev("vsource", "V1", -200, 0, 1.8)
    s.lines.append("C {kv_ref.sym} 100 0 0 0 {name=x1}")
    s.dev("res", "R2", 300, 60, "50k")
    s.wire((-200, -30), (-200, -120), (100, -120), (100, -60), net="vdd")
    s.wire((180, 0), (300, 0), (300, 30), net="iout")
    s.wire((-200, 160), (300, 160), net="0")
    for x, y in ((-200, 30), (100, 60), (300, 90)):
        s.wire((x, y), (x, 160), net="0")
    s.lab(-200, -120, "vdd"); s.lab(300, 0, "iout", flip=1); s.lab(-200, 160, "0")
    s.lines.append("C {sky130_fd_pr/corner.sym} -200 -300 0 0 {name=CORNER only_toplevel=true corner=tt}")
    s.lines.append('C {devices/code_shown.sym} -200 260 0 0 {name=s1 only_toplevel=false value=".op\n.save all"}')
    return s.text()


def amp():
    """kv_amp.sch: two-stage Miller op-amp, ports vdd, vss, inp, inn, out, drawn with wires; 20 uA bias into its own
    diode; Cc 0.5 pF (too small for 10 pF: thin phase margin, on purpose) with a 2 kOhm zero resistor."""
    s = Sheet()
    for x, y, net in ((-300, -120, "vdd"), (-300, 520, "vss"), (-300, 170, "inp"), (-300, 230, "inn"), (620, 290, "out")):
        s.pin(x, y, net)
    s.mos(P, "M3", 0, 0, "vdd", 8, 1); s.mos(P, "M4", 200, 0, "vdd", 8, 1); s.mos(P, "M7", 460, 0, "vdd", 32, 0.5)
    s.mos(N, "M1", 0, 230, "vss", 8, 1); s.mos(N, "M2", 200, 230, "vss", 8, 1)
    s.mos(N, "M5", 120, 380, "vss", 8, 1); s.mos(N, "M6", -160, 380, "vss", 4, 1); s.mos(N, "M8", 460, 380, "vss", 16, 1)
    s.dev("isource", "I1", -140, 60, "20u"); s.dev("capa", "C1", 360, 120, "0.5p"); s.dev("res", "R1", 360, 230, "2k")
    s.wire((-300, -120), (480, -120), net="vdd")
    for x, y in ((20, -30), (220, -30), (480, -30), (-140, 30)):
        s.wire((x, -120), (x, y), net="vdd")
    s.wire((-300, 520), (480, 520), net="vss")
    for x in (-140, 140, 480):
        s.wire((x, 410), (x, 520), net="vss")
    s.wire((20, 30), (20, 200), net="o1")                                        # first stage, mirror load
    s.wire((-20, 0), (-40, 0), (-40, 100), (20, 100), net="o1")
    s.wire((180, 0), (160, 0), (160, 100), (20, 100), net="o1")
    s.wire((220, 30), (220, 200), net="o2a")
    s.wire((440, 0), (400, 0), (400, 60), (220, 60), net="o2a")
    s.wire((360, 90), (360, 60), net="o2a")
    s.wire((360, 150), (360, 200), net="ncz")                                    # Miller capacitor and its zero resistor
    s.wire((480, 30), (480, 350), net="out")
    s.wire((360, 260), (360, 290), (480, 290), net="out"); s.wire((480, 290), (620, 290), net="out")
    s.wire((20, 230 + 30), (20, 300), (220, 300), net="tail"); s.wire((220, 260), (220, 300), net="tail")
    s.wire((140, 300), (140, 350), net="tail")
    s.wire((-140, 90), (-140, 350), net="vb")                                    # bias: I1 into the M6 diode
    s.wire((-180, 380), (-200, 380), (-200, 330), (-140, 330), net="vb")
    s.wire((-200, 380), (-200, 460), (420, 460), net="vb")
    s.wire((100, 380), (80, 380), (80, 460), net="vb"); s.wire((440, 380), (420, 380), (420, 460), net="vb")
    s.wire((-20, 230), (-300, 230), net="inn")
    s.wire((180, 230), (160, 230), (160, 170), (-300, 170), net="inp")
    s.lab(-40, 100, "o1"); s.lab(400, 0, "o2a"); s.lab(20, 300, "tail"); s.lab(-200, 460, "vb"); s.lab(360, 175, "ncz", flip=1)
    return s.text()


AMP_SYM = """v {xschem version=3.4.5 file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x2"
}
V {}
S {}
E {}
L 4 -60 -50 -60 50 {}
L 4 -60 50 60 0 {}
L 4 60 0 -60 -50 {}
B 5 -2.5 -62.5 2.5 -57.5 {name=vdd dir=inout}
B 5 -2.5 57.5 2.5 62.5 {name=vss dir=inout}
B 5 -82.5 17.5 -77.5 22.5 {name=inp dir=in}
B 5 -82.5 -22.5 -77.5 -17.5 {name=inn dir=in}
B 5 77.5 -2.5 82.5 2.5 {name=out dir=out}
T {@symname} -40 -10 0 0 0.3 0.3 {}
T {@name} 10 -70 0 0 0.2 0.2 {}
"""


def amp_testbench():
    """tb_amp.sch: the op-amp as a unity follower (out wired back to inn) at 1.8 V, input at mid-supply, 10 pF load."""
    s = Sheet()
    s.dev("vsource", "V1", -300, 0, 1.8); s.dev("vsource", "V2", -160, 80, 0.9)
    s.lines.append("C {kv_amp.sym} 100 0 0 0 {name=x2}")
    s.dev("capa", "C2", 300, 60, "10p")
    s.wire((-300, -30), (-300, -160), (100, -160), (100, -60), net="vdd")
    s.wire((180, 0), (220, 0), net="out"); s.wire((220, 0), (300, 0), (300, 30), net="out")
    s.wire((220, 0), (220, -120), (-20, -120), (-20, -20), (20, -20), net="out")   # the feedback: out to inn
    s.wire((-160, 50), (-160, 20), (20, 20), net="inp")
    s.wire((-300, 200), (300, 200), net="0")
    for x, y in ((-300, 30), (-160, 110), (100, 60), (300, 90)):
        s.wire((x, y), (x, 200), net="0")
    s.lab(-300, -160, "vdd"); s.lab(300, 0, "out", flip=1); s.lab(-160, 20, "inp"); s.lab(-300, 200, "0")
    s.lines.append("C {sky130_fd_pr/corner.sym} -300 -320 0 0 {name=CORNER only_toplevel=true corner=tt}")
    s.lines.append('C {devices/code_shown.sym} -300 300 0 0 {name=s1 only_toplevel=false value=".op\n.save all"}')
    return s.text()


def bias():
    """kv_bias.sch: a resistor-set current mirror, ports vdd, vss, ibias, drawn with wires. Its transistors are sized
    SI-style (W=2u L=1u, on purpose): sky130 reads W and L in micrometres, so they simulate 2e-6 um wide."""
    s = Sheet()
    s.pin(-200, -100, "vdd"); s.pin(-200, 300, "vss"); s.pin(300, 0, "ibias")
    s.dev("res", "R1", 0, 0, "10k")
    s.mos(N, "M1", -20, 150, "vss", "2u", "1u"); s.mos(N, "M2", 180, 150, "vss", "2u", "1u")
    s.wire((-200, -100), (0, -100), (0, -30), net="vdd")
    s.wire((0, 30), (0, 120), net="nb")
    s.wire((-40, 150), (-60, 150), (-60, 80), (0, 80), net="nb")
    s.wire((160, 150), (140, 150), (140, 80), (0, 80), net="nb")
    s.wire((200, 120), (200, 0), (300, 0), net="ibias")
    s.wire((-200, 300), (200, 300), net="vss"); s.wire((0, 180), (0, 300), net="vss"); s.wire((200, 180), (200, 300), net="vss")
    s.lab(-60, 80, "nb")
    return s.text()


def bias_testbench():
    """tb_bias.sch: 1.8 V, the mirror sinking its current from a 5 kOhm load on ibias; the operating point."""
    s = Sheet()
    s.dev("vsource", "V1", -200, 0, 1.8)
    s.lines.append("C {kv_bias.sym} 100 0 0 0 {name=x3}")
    s.dev("res", "R2", 300, -60, "5k")
    s.wire((-200, -30), (-200, -120), (300, -120), (300, -90), net="vdd"); s.wire((100, -120), (100, -60), net="vdd")
    s.wire((180, 0), (300, 0), (300, -30), net="ibias")
    s.wire((-200, 160), (100, 160), net="0"); s.wire((-200, 30), (-200, 160), net="0"); s.wire((100, 60), (100, 160), net="0")
    s.lab(-200, -120, "vdd"); s.lab(300, 0, "ibias", flip=1); s.lab(-200, 160, "0")
    s.lines.append("C {sky130_fd_pr/corner.sym} -200 -300 0 0 {name=CORNER only_toplevel=true corner=tt}")
    s.lines.append('C {devices/code_shown.sym} -200 260 0 0 {name=s1 only_toplevel=false value=".op\n.save all"}')
    return s.text()


VERILOG = """`default_nettype none
// Kaaval demo tile: two analog blocks, the current reference (xschem/kv_ref.sch, output on ua[0]) and an op-amp
// follower (xschem/kv_amp.sch, input ua[1], output ua[2]) and a bias mirror (xschem/kv_bias.sch, ua[3]).
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
  kv_amp a0 (.vdd(VDPWR), .vss(VGND), .inp(ua[1]), .inn(ua[2]), .out(ua[2]));
  kv_bias b0 (.vdd(VDPWR), .vss(VGND), .ibias(ua[3]));
endmodule
"""

INFO = """# Kaaval demo tile (ours): a Tiny Tapeout-shaped analog project, never submitted to a shuttle.
project:
  title: "Kaaval demo: current reference and op-amp follower"
  author: "Sanjay Sivakumar"
  description: "A current reference with no start-up device and an under-compensated op-amp, on purpose: Kaaval's demo design."
  language: "Analog"
  tiles: "1x2"
  analog_pins: 4
  uses_3v3: false
  top_module: "tt_um_kaaval_demo"
pinout:
  ua[0]: "iout: reference current into the load"
  ua[1]: "inp: op-amp follower input"
  ua[2]: "out: op-amp follower output"
  ua[3]: "ibias: bias mirror output"
"""

README = """# Kaaval demo tile

A Tiny Tapeout-shaped analog project **of our own**, made for Kaaval's demos (written by `tools/make_demo_tapeout.py`):
three analog blocks, schematics drawn with wires (`xschem/`), two of them also drawn as sky130 layouts with Magic
(`mag/`, and the whole tile in `mag/tt_um_kaaval_demo.mag`). Every block has flaws **on purpose**; review it by
uploading a zip of this folder.

| Block | Planted flaw | What a review should find |
|---|---|---|
| `kv_ref`, a self-biased (beta-multiplier) current reference | no start-up device | powered up from 0 V it stays at zero current at most conditions (DC analysis still finds the working bias) |
| `kv_amp`, a two-stage Miller op-amp | 0.5 pF compensation for a 10 pF load | `tb_amp.sch` wires it as a unity follower: that loop's phase margin is thin |
| `kv_amp` layout | M8 drawn 12 um wide, 16 um in the schematic | layout against schematic: the sizes differ |
| `kv_bias`, a resistor-set current mirror | sized SI-style, `W=2u L=1u` | sky130 reads W and L in micrometres, so these are 2e-6 um wide: a units trap |

The layouts draw only the transistors: the schematics' resistors, capacitor and current source are ideal parts with no
PDK model. Testbenches: `tb_ref.sch`, `tb_amp.sch`, `tb_bias.sch` (1.8 V, operating point). Never submitted to a shuttle.
"""


# ---- layout: the transistors of kv_ref and kv_amp drawn in sky130 with Magic (the ideal R, C and current source of
# the schematics have no layout shape, as Kaaval's layout check notes). One NMOS row (gates and tracks below it), one
# PMOS row in an nwell (gates and tracks above it); every net is a metal1 track, each transistor terminal reaches its
# track by a local-interconnect stub and a via, and a net used by both rows climbs a metal2 riser on the right.
REF_DEVS = [("M3", "p", 8, 2, "n1", "n2", "vdd"), ("M4", "p", 8, 2, "n2", "n2", "vdd"), ("M5", "p", 8, 2, "iout", "n2", "vdd"),
            ("M1", "n", 4, 2, "n1", "n1", "vss"), ("M2", "n", 16, 2, "n2", "n1", "s2")]
AMP_DEVS = [("M3", "p", 8, 1, "o1", "o1", "vdd"), ("M4", "p", 8, 1, "o2a", "o1", "vdd"), ("M7", "p", 32, 0.5, "out", "o2a", "vdd"),
            ("M6", "n", 4, 1, "vb", "vb", "vss"), ("M5", "n", 8, 1, "tail", "vb", "vss"), ("M1", "n", 8, 1, "o1", "inn", "tail"),
            ("M2", "n", 8, 1, "o2a", "inp", "tail"), ("M8", "n", 12, 1, "out", "vb", "vss")]
# M8 is drawn 12 um wide where the schematic says 16 (on purpose): a layout that differs from its schematic


def layout_tcl(cell, devs, ports):
    """The Magic script that draws `cell`: devs [(name, n|p, W, L, drain, gate, source)], bodies to vss / vdd."""
    out = [f"load {cell} -force", "proc r {l x1 y1 x2 y2} { box ${x1}um ${y1}um ${x2}um ${y2}um; paint $l }"]
    R = lambda l, x1, y1, x2, y2: out.append(f"r {l} {x1:.3f} {y1:.3f} {x2:.3f} {y2:.3f}")
    rows = {k: [d for d in devs if d[1] == k] for k in "np"}
    wn = max(d[2] for d in rows["n"]); wp = max(d[2] for d in rows["p"])
    yp = wn + 5.0                                          # PMOS diffusion bottom
    stubs = {"n": {}, "p": {}}                             # row -> net -> [x centre of each stub]
    xmax = 0.0
    for k in "np":
        x = 0.0
        y0 = 0.0 if k == "n" else yp
        diff, dc, sub, subc = (("ndiff", "ndiffc", "psubdiff", "psubdiffcont") if k == "n" else
                               ("pdiff", "pdiffc", "nsubdiff", "nsubdiffcont"))
        R(sub, -3.0, y0, -2.4, y0 + 2.0); R(subc, -2.87, y0 + 0.2, -2.53, y0 + 1.8)        # the body tap
        stubs[k].setdefault("vss" if k == "n" else "vdd", []).append(-2.7)
        for name, _, W, L, dn, gn, sn in rows[k]:
            R(diff, x, y0, x + L + 1.2, y0 + W)
            gy = (y0 - 1.3, y0 + 0.3) if k == "n" else (y0 + W - 0.3, y0 + W + 1.3)
            R("poly", x + 0.6, min(gy[0], y0 - 0.3), x + 0.6 + L, max(gy[1], y0 + W + 0.3) if k == "p" else y0 + W + 0.3)
            xc = x + 0.6 + L / 2
            pad = (y0 - 1.3, y0 - 0.5) if k == "n" else (y0 + W + 0.5, y0 + W + 1.3)
            R("poly", xc - 0.4, pad[0], xc + 0.4, pad[1]); R("polycont", xc - 0.25, pad[0] + 0.15, xc + 0.25, pad[1] - 0.15)
            for cx, net in ((x + 0.3, sn), (x + L + 0.9, dn)):
                R(dc, cx - 0.17, y0 + 0.2, cx + 0.17, y0 + W - 0.2)
                stubs[k].setdefault(net, []).append(cx)
            stubs[k].setdefault(gn, []).append(xc)
            x += L + 1.2 + 1.6
        xmax = max(xmax, x)
    tracks = {}                                            # (row, net) -> y of its metal1 track
    for k in "np":
        order = sorted(stubs[k], key=lambda n: (-len(stubs[k][n]), n))
        for i, net in enumerate(order):
            tracks[(k, net)] = -3.0 - 1.2 * i if k == "n" else yp + wp + 3.5 + 1.2 * i
    shared = sorted(n for (k, n) in tracks if k == "n" and ("p", n) in tracks)
    riser = {n: xmax + 1.0 + 1.4 * j for j, n in enumerate(shared)}
    for (k, net), ty in tracks.items():
        y0 = 0.0 if k == "n" else yp
        xs = stubs[k][net]
        for cx in xs:                                      # stub from the contact (or gate pad) to the track, and a via
            if k == "n":
                R("locali", cx - 0.17, ty - 0.17, cx + 0.17, y0 + 0.4)
            else:
                R("locali", cx - 0.17, y0 + 0.4, cx + 0.17, ty + 0.17)
            R("viali", cx - 0.15, ty - 0.15, cx + 0.15, ty + 0.15)
        hi = max(xs + ([riser[net]] if net in riser else []))
        R("metal1", min(xs) - 0.35, ty - 0.25, hi + 0.35, ty + 0.25)
    for net, xr in riser.items():                          # a net of both rows: metal2 up the right-hand side
        a, b = tracks[("n", net)], tracks[("p", net)]
        R("metal2", xr - 0.2, a - 0.2, xr + 0.2, b + 0.2)
        for ty in (a, b):
            R("via1", xr - 0.15, ty - 0.15, xr + 0.15, ty + 0.15)
    R("nwell", -4.0, yp - 1.5, xmax + 0.5, yp + wp + 2.0)
    for net in ports:                                      # each port labelled on its track, as a port
        k = "n" if ("n", net) in tracks else "p"
        ty, xl = tracks[(k, net)], min(stubs[k][net]) - 0.2
        out += [f"box {xl:.3f}um {ty:.3f}um {xl:.3f}um {ty:.3f}um", f"label {net} c metal1", "port make"]
    for (k, net), ty in tracks.items():                    # internal nets named too, for readable extraction
        if net not in ports:
            xl = min(stubs[k][net]) - 0.2
            out += [f"box {xl:.3f}um {ty:.3f}um {xl:.3f}um {ty:.3f}um", f"label {net} c metal1"]
    out += [f"save {cell}"]
    return "\n".join(out) + "\n"


def layouts(out_dir):
    """Draw mag/kv_ref.mag, mag/kv_amp.mag and the tile mag/tt_um_kaaval_demo.mag (both blocks placed) with Magic."""
    import shutil, subprocess, sys, tempfile
    sys.path.insert(0, HERE)
    from kaaval_engine.paths import PDK_ROOT
    rc = os.path.join(PDK_ROOT, "libs.tech", "magic", "sky130A.magicrc")
    if not shutil.which("magic") or not os.path.isfile(rc):
        print("Magic or the sky130 magicrc is missing: layouts not redrawn")
        return
    mag = os.path.join(out_dir, "mag")
    os.makedirs(mag, exist_ok=True)
    script = (layout_tcl("kv_ref", REF_DEVS, ["vdd", "vss", "iout"]) + layout_tcl("kv_amp", AMP_DEVS, ["vdd", "vss", "inp", "inn", "out"]) +
              "load tt_um_kaaval_demo -force\nbox 0um 0um 0um 0um\ngetcell kv_ref\nbox 40um 0um 40um 0um\ngetcell kv_amp\n"
              "save tt_um_kaaval_demo\nquit -noprompt\n")
    with tempfile.TemporaryDirectory() as t:
        open(os.path.join(t, "draw.tcl"), "w").write(script)
        env = dict(os.environ, PDK_ROOT=os.path.dirname(PDK_ROOT), PDK=os.path.basename(PDK_ROOT))
        subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", rc, "draw.tcl"], cwd=t, env=env, check=True,
                       capture_output=True, stdin=subprocess.DEVNULL, timeout=300)
        for f in ("kv_ref.mag", "kv_amp.mag", "tt_um_kaaval_demo.mag"):
            text = re.sub(r"(?m)^timestamp \d+$", "timestamp 0", open(os.path.join(t, f)).read())
            open(os.path.join(mag, f), "w").write(text)


def main():
    files = {"xschem/kv_ref.sch": block(), "xschem/kv_ref.sym": SYM, "xschem/tb_ref.sch": testbench(),
             "xschem/kv_amp.sch": amp(), "xschem/kv_amp.sym": AMP_SYM, "xschem/tb_amp.sch": amp_testbench(),
             "xschem/kv_bias.sch": bias(), "xschem/kv_bias.sym": SYM.replace("iout", "ibias").replace("name=x1", "name=x3"),
             "xschem/tb_bias.sch": bias_testbench(),
             "src/project.v": VERILOG, "info.yaml": INFO, "README.md": README}
    for rel, text in files.items():
        p = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)
    layouts(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

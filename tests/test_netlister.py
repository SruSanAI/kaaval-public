"""The text-only netlister follows xschem's rules: bus pins and instance arrays expand bit by bit, a sub-circuit's
header carries its symbol's extra= ports and the template defaults its format passes in, and a real schematic
netlists without error."""
import os, re, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import netlist as N

SYM = """v {xschem version=3.4.5 file_version=1.2}
K {type=subcircuit
format="@name @pinlist @VCCPIN @symname W=@W m=@m"
template="name=x1 m=1 W=2 VCCPIN=VCC"
extra="VCCPIN"
}
B 5 -2.5 -2.5 2.5 2.5 {name=d[1:0] dir=in}
B 5 17.5 -2.5 22.5 2.5 {name=y dir=out}
"""


def test_expand():
    assert N.expand("a[3:0]") == ["a[3]", "a[2]", "a[1]", "a[0]"]
    assert N.expand("a[0:2]") == ["a[0]", "a[1]", "a[2]"]
    assert N.expand("x,b[1:0]") == ["x", "b[1]", "b[0]"]
    assert N.expand("net1") == ["net1"] and N.expand("a[2]") == ["a[2]"]


def test_subckt_header_like_xschem():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "cell.sym"), "w").write(SYM)
    open(os.path.join(d, "cell.sch"), "w").write("v {xschem version=3.4.5 file_version=1.2}\n")
    sd = N.symbol(os.path.join(d, "cell.sym"))
    head = [l for l in N._subckt(os.path.join(d, "cell.sch"), "cell", sd, {}) if l.startswith(".subckt")][0]
    assert head == ".subckt cell d[1] d[0] y VCCPIN W=2", head


def test_real_schematic_if_present():
    p = os.environ.get("KAAVAL_REAL_SCH", "")
    if not os.path.exists(p):
        print("skip: corpus not on this machine")
        return
    net = N.netlist(p)
    assert sum(1 for l in net.splitlines() if l.startswith("XM")) > 40


def test_repeated_property_keeps_its_first_value():
    """An instance whose property block repeats name= (pin attributes pasted after name=X_CORE) is named by the first,
    as xschem names it; the last one once turned a subcircuit X_CORE into a 'voltage source' V_TRIG with two nets."""
    from kaaval_engine import sch as S, xsch as X
    props = "name=X_CORE\n\nname=V_THRESH dir=in sim_pinnumber=0\nname=V_TRIG dir=inout sim_pinnumber=5\n"
    assert X._props(props)["name"] == "X_CORE" and S.attrs(props)["name"] == "X_CORE"
    import tempfile
    d = tempfile.mkdtemp()
    open(os.path.join(d, "r.sch"), "w").write(
        "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
        "C {devices/res.sym} 0 0 0 0 {name=R1\nname=V_JUNK value=1k}\n"
        "C {devices/lab_pin.sym} 0 -30 0 0 {name=p1 lab=a}\nC {devices/lab_pin.sym} 0 30 0 0 {name=p2 lab=b}\n")
    text = N.netlist(os.path.join(d, "r.sch"))
    assert re.search(r"^R1 a b 1k", text, re.M) and "V_JUNK" not in text, text
def test_bus_ranges_with_two_dots():
    """xschem writes bus ranges as a[6:0] or a[6..0]; with '..' an instance array xcell[3..0] was one instance with
    bus nets (a layout check then saw 50 devices against 8). Each copy takes its bits, in order."""
    assert N.expand("v[2..0],IN") == ["v[2]", "v[1]", "v[0]", "IN"] and N.expand("c[0..1]") == ["c[0]", "c[1]"]
    assert N.expand("v[2:0]") == N.expand("v[2..0]")


def test_global_supply_label_reaches_sub_circuits():
    """A sub-circuit powered by a vdd.sym label (global=true) shares the top's VDD, as xschem makes it with .GLOBAL;
    without it the sub-circuit's VDD was a local, unconnected net and its divider sat at 0 V in simulation."""
    import subprocess
    from kaaval_engine import sim
    d = tempfile.mkdtemp()
    head = "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
    open(os.path.join(d, "div.sym"), "w").write(
        "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {type=subcircuit\nformat=\"@name @pinlist @symname\"\n"
        "template=\"name=x1\"\n}\nV {}\nS {}\nE {}\nB 5 -2.5 -2.5 2.5 2.5 {name=mid dir=out}\n")
    open(os.path.join(d, "div.sch"), "w").write(head +
        "C {devices/res.sym} 0 0 0 0 {name=R1 value=1k}\nC {devices/vdd.sym} 0 -30 0 0 {name=l1 lab=VDD}\n"
        "C {devices/lab_pin.sym} 0 30 0 0 {name=p1 lab=mid}\n"
        "C {devices/res.sym} 0 90 0 0 {name=R2 value=1k}\nC {devices/lab_pin.sym} 0 60 0 0 {name=p2 lab=mid}\n"
        "C {devices/gnd.sym} 0 120 0 0 {name=l2 lab=GND}\nC {devices/opin.sym} 100 0 0 0 {name=p3 lab=mid}\n")
    open(os.path.join(d, "tb.sch"), "w").write(head +
        "C {div.sym} 0 0 0 0 {name=x1}\nC {devices/lab_pin.sym} 0 0 0 0 {name=p1 lab=out}\n"
        "C {devices/vsource.sym} 200 0 0 0 {name=V1 value=1.8}\nC {devices/vdd.sym} 200 -30 0 0 {name=l1 lab=VDD}\n"
        "C {devices/gnd.sym} 200 30 0 0 {name=l2 lab=GND}\n")
    text = N.netlist(os.path.join(d, "tb.sch"))
    assert ".GLOBAL VDD" in text.splitlines(), text
    if shutil.which("ngspice"):
        deck = text + "\n.control\nop\nprint v(out)\n.endc\n.end\n"
        open(os.path.join(d, "d.sp"), "w").write("* tb\n" + deck)
        out = subprocess.run(["ngspice", "-b", os.path.join(d, "d.sp")], capture_output=True, text=True).stdout
        assert re.search(r"v\(out\) = 9\.0+e-01", out), out[-400:]


def test_code_block_devices_in_a_sub_cell():
    """A cell drawn as pins plus a code_shown block of transistor lines (only_toplevel=false): xschem copies the device
    lines into the sub-circuit, so do we; its .control lines and dot-commands stay out, and at the top level the block
    is still dropped (2 Nov: a design drawing its standard cells this way came out as empty cells)."""
    d = tempfile.mkdtemp()
    head = "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
    open(os.path.join(d, "inv.sym"), "w").write(
        "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {type=subcircuit\nformat=\"@name @pinlist @symname\"\n"
        "template=\"name=x1\"\n}\nV {}\nS {}\nE {}\nB 5 -2.5 -2.5 2.5 2.5 {name=A dir=in}\n"
        "B 5 7.5 -2.5 12.5 2.5 {name=Y dir=out}\n")
    code = ('C {devices/code_shown.sym} 0 0 0 0 {name=s1 only_toplevel=false value="\n'
            'X0 Y A VPWR VPWR sky130_fd_pr__pfet_01v8 w=0.42 l=0.15\n'
            'X1 Y A VGND VGND sky130_fd_pr__nfet_01v8\n+ w=0.42 l=0.15\n.include evil.spice\n.control\nshell rm x\n.endc\n"}\n')
    open(os.path.join(d, "inv.sch"), "w").write(head + code +
        "C {devices/ipin.sym} -100 0 0 0 {name=p1 lab=A}\nC {devices/opin.sym} 100 0 0 0 {name=p2 lab=Y}\n")
    open(os.path.join(d, "top.sch"), "w").write(head + code.replace("name=s1", "name=s2") +
        "C {inv.sym} 0 0 0 0 {name=x1}\n")
    text = N.netlist(os.path.join(d, "top.sch"))
    body = text.split(".subckt inv", 1)[1].split(".ends", 1)[0]
    assert "X0 Y A VPWR VPWR sky130_fd_pr__pfet_01v8 w=0.42 l=0.15" in body, text
    assert "X1 Y A VGND VGND sky130_fd_pr__nfet_01v8 w=0.42 l=0.15" in body, text
    assert ".include" not in text and "shell" not in text and ".control" not in text, text
    assert text.count("sky130_fd_pr__pfet_01v8") == 1, text           # the top level's own block is not copied


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

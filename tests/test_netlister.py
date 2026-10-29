"""The text-only netlister follows xschem's rules: bus pins and instance arrays expand bit by bit, a sub-circuit's
header carries its symbol's extra= ports and the template defaults its format passes in, and a real schematic
netlists without error."""
import os, sys, tempfile
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

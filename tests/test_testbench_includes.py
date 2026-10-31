"""A testbench that takes its sources from a file it .includes: Kaaval never reads the file, so a failed operating
point must say the sources live there, and name a file that is not in the repository at all. No simulation."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import sim  # noqa: E402

SCH = """v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/res.sym} 0 0 0 0 {name=R1 value=1k}
C {devices/lab_pin.sym} 0 -30 0 0 {name=p1 lab=vcc}
C {devices/lab_pin.sym} 0 30 0 0 {name=p2 lab=0}
C {devices/code.sym} -200 0 0 0 {name=stimuli only_toplevel=false value="
.include stimuli_tb.cir
.include \\"models_here.spice\\"
.op
"}
"""


def test_includes_are_named_never_read():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "tb.sch"), "w").write(SCH)
    open(os.path.join(d, "models_here.spice"), "w").write("* present\n")
    tb = sim.Testbench.from_sch(os.path.join(d, "tb.sch"))
    assert tb.includes == ["stimuli_tb.cir", "models_here.spice"], tb.includes
    assert tb.analyses == [".op"]
    note = tb.include_note()
    assert "stimuli_tb.cir, models_here.spice" in note and "does not read" in note
    assert "stimuli_tb.cir is not in the repository" in note and "models_here.spice is not" not in note, note
    assert ".include" not in sim.deck(tb, "tt", 27, 1.0).lower()


def test_no_includes_no_note():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "tb.sch"), "w").write(SCH.replace(".include stimuli_tb.cir\n", "").replace(
        '.include \\"models_here.spice\\"\n', ""))
    tb = sim.Testbench.from_sch(os.path.join(d, "tb.sch"))
    assert tb.includes == [] and tb.include_note() == ""


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

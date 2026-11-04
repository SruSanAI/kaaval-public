"""app/sizing.py: Muse Spark's W / L proposals are written into the block's xschem schematic, only on the named
instances, and refused outside the allowed range. No model, no simulation."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import sizing  # noqa: E402

SCH = ("v {xschem version=3.4.5 file_version=1.2}\n"
       "C {sky130_fd_pr/pfet_01v8.sym} 0 0 0 0 {name=M3\nW=8\nL=1\nnf=1\nmodel=pfet_01v8\n}\n"
       "C {sky130_fd_pr/nfet_01v8.sym} 0 200 0 0 {name=M1 L=1 W=8 nf=1 model=nfet_01v8}\n"
       "C {devices/res.sym} 220 300 0 0 {name=R1 value=20k}\n")


def test_apply_writes_only_the_named_devices():
    new, done, errors = sizing.apply({"b.sch": SCH}, "b.sch", [{"device": "x2.xm3", "W": 24, "L": 1},
                                                              {"device": "M1", "W": 16, "L": 0.5}])
    t = new["b.sch"]
    assert not errors and [d["device"] for d in done] == ["M3", "M1"], (done, errors)
    assert "{name=M3\nW=24\nL=1\n" in t and "{name=M1 L=0.5 W=16 nf=1" in t and "{name=R1 value=20k}" in t
    assert done[0]["before"] == "W=8 L=1" and done[0]["after"] == "W=24 L=1"


def test_apply_refuses_unknown_and_out_of_range():
    _, done, errors = sizing.apply({"b.sch": SCH}, "b.sch", [{"device": "M9", "W": 4, "L": 1},
                                                            {"device": "M1", "W": 500, "L": 1}])
    assert not done and len(errors) == 2 and "M9" in errors[0] and "outside" in errors[1], errors


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

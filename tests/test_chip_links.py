"""app/server._belongs: which chip block a stored finding is drawn on, so the chip view, the bench and the walk-through
show the same finding by its id. No simulation."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import server  # noqa: E402

LV = dict(dut="xschem/opamp.sch")


def test_each_kind_of_finding_lands_on_its_block():
    planned = dict(rule="analog/two_states", kind="risk", detail=dict(plan=dict(cell="xschem/Core.sch")))
    loop = dict(rule="analog/low_phase_margin", kind="risk", detail=dict(loop=dict(subckt="p3_opamp"), testbench="xschem/tb.sch"))
    lay = dict(rule="layout/sizes_differ", kind="risk", detail=dict(sch="xschem/ladder.sch"))
    pvt = dict(rule="analog/headroom", kind="risk", detail=dict(device="x1.xm3"))
    trap = dict(rule="units/scale", kind="trap", detail={})
    b = server._belongs
    assert b(planned, "xschem/core.sch", LV) and not b(planned, "xschem/opamp.sch", LV)
    assert b(loop, "xschem/p3_opamp.sch", LV) and not b(loop, "xschem/tb.sch", LV)
    assert b(lay, "xschem/ladder.sch", LV) and b(pvt, "xschem/opamp.sch", LV) and not b(pvt, "xschem/core.sch", LV)
    assert not b(trap, "xschem/opamp.sch", LV) and not b(planned, "", LV)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

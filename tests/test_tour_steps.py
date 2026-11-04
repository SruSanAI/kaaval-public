"""app/static/tour.js under node: each kind of finding becomes the right walk-through steps, every number taken from
the finding itself, and a step whose target the finding does not have is left out. Skipped where node is missing."""
import json, os, shutil, subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOUR = os.path.join(HERE, "app", "static", "tour.js")

FINDINGS = {
    "loop": dict(rule="analog/low_phase_margin", kind="risk", device="x1", title="In the designer's own testbench, x1 (p3_opamp) in "
                 "feedback. The loop has thin margins.", detail=dict(loop=dict(inst="x1", subckt="p3_opamp", net="VOUT", pin="x1.2",
                 via="back to its pin 4 (VOUT) directly"), testbench="xschem/tb.sch", worst=["sf", -40, 1.1], n_bad=45, n=45,
                 margins=dict(pm=1.2, ugf=1.53e9), results=[])),
    "headroom": dict(rule="analog/headroom", kind="risk", device="x1.xm30", title="x1.xm30 is in saturation at nominal.",
                     detail=dict(device="x1.xm30", nominal_margin=0.12, worst_margin=-0.03, worst=["ss", -40, 0.9], n_bad=6, n=45)),
    "planned": dict(rule="analog/two_states", kind="risk", device="supply", title="Powered up from 0 V, it settles elsewhere.",
                    detail=dict(k=0, plan=dict(cell="xschem/core.sch", kind="powerup"), worst=["tt", 27, 1.0], n_bad=3, n=30,
                                states=[dict(i=7.2e-6), dict(i=3.3e-10)])),
    "layout": dict(rule="layout/sizes_differ", kind="risk", device="opamp", title="opamp: the layout draws other sizes.", detail=dict(cell="opamp")),
    "note": dict(rule="analog/oscillates", kind="note", device="OUT", title="It swings. Held, it settles.",
                 detail=dict(k=1, plan=dict(cell="xschem/nor.sch"), worst=["tt", 27, 1.0], n_bad=2, n=30)),
}


def run():
    js = f"const T = require({json.dumps(TOUR)}); const F = {json.dumps(FINDINGS)};" \
         "const out = {}; for (const k in F) out[k] = T.steps(F[k], 'PLAIN.'); console.log(JSON.stringify(out));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def test_steps_per_kind_of_finding():
    if not shutil.which("node"):
        print("skip: node not installed")
        return
    s = run()
    ids = {k: [x["id"] for x in v] for k, v in s.items()}
    assert ids["loop"] == ["what", "where", "when", "proof", "next"], ids
    assert ids["headroom"] == ["what", "where", "when", "next"], ids          # the PVT sweep is its proof: no evidence panel
    assert ids["layout"] == ["what", "next"], ids                            # the layout is not drawn on the bench
    loop = {x["id"]: x for x in s["loop"]}
    assert loop["where"]["target"] == dict(kind="device", sheet="xschem/tb.sch", device="x1", text=loop["where"]["text"])
    assert loop["where"]["callout"] == "phase margin 1° at 1.53 GHz (sf, -40 °C, supply ×1.1)", loop["where"]["callout"]
    assert "45 of 45 conditions" in loop["when"]["text"] and loop["what"]["text"].startswith("PLAIN. ")
    head = {x["id"]: x for x in s["headroom"]}
    assert head["where"]["callout"] == "margin 120 mV at nominal, -30 mV at ss, -40 °C, supply ×0.9", head["where"]["callout"]
    assert head["when"]["target"]["kind"] == "cells" and "sizing fix" in head["next"]["text"]
    pl = {x["id"]: x for x in s["planned"]}
    assert pl["where"]["target"]["kind"] == "sheet" and pl["where"]["callout"] == "7.20 µA by DC analysis, 330 pA after power-up"
    assert "Download the evidence" in pl["next"]["text"]
    assert "This is a note" in {x["id"]: x for x in s["note"]}["next"]["text"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

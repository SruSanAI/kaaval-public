"""twin.py — Silicon Twin: from what the fabricated chip did on the bench back to a cause in its circuit.

A bring-up report says what silicon showed at one node ("Vbgr reads 1.17 V at first, then 0.46 V depending on the
meter"). The twin rebuilds the block in its chip context and searches the contexts a bench changes: the load on the
node (open, a 10 Mohm meter, 1 Mohm, 100 kohm, 10 kohm), the power-up from 0 V (every result step-checked,
sim.startup_checked), and the process corners. Every simulated state is compared with every measured value:

  dc        the block's DC answer under that load matches: the measurement is the load's doing (output resistance)
  powerup   the state a power-up from 0 V lands in matches while the DC answer does not: the chip came up in another
            operating point (a start-up problem), not a measurement artefact

A measurement no context reproduces is reported as not reproduced; nothing is fitted or tuned to match.

    symptom = {"cell": "xschem/core_prel.sch", "supplies": {"VDD": 1.8}, "grounds": ["VSS"], "node": "Vbgr",
               "measured": [1.17, 0.46], "pad": True}
    result = search(symptom, root)
"""
from kaaval_engine import plan as P

LOADS = [None, 1e7, 1e6, 1e5, 1e4]
CORNERS = ["tt", "ss", "ff"]


def _tol(v):
    return max(0.1 * abs(v), 0.05)


def search(symptom, root, corners=CORNERS, temps=(27,), loads=LOADS, on_result=None):
    """{ok, contexts: [{load, corner, temp, dc, powerup, error}], matches: [{measured, how, load, corner, temp,
    simulated}], unmatched: [measured], errors} for one symptom."""
    node = symptom["node"]
    base = dict(cell=symptom["cell"], kind="powerup", supplies=symptom["supplies"], grounds=symptom.get("grounds") or [],
                biases=symptom.get("biases") or [], pads=[{"port": node}] if symptom.get("pad", True) else [],
                corners=list(corners), temps=list(temps), vscales=[1.0])
    errs = P.validate(base, root)
    if errs:
        return dict(ok=False, errors=errs)
    contexts = []
    for load in loads:
        pl = dict(base, loads=[{"port": node, "ohms": load}] if load else [])
        r = P.run(pl, root, on_result=on_result)
        if not r.get("ok"):
            return dict(ok=False, errors=r.get("errors"))
        for x in r["results"]:
            v = _node(x.get("nodes"), node)
            contexts.append(dict(load=load, corner=x["corner"], temp=x["temp"], error=x["error"],
                                 dc=v[0] if v else None, powerup=v[1] if v else None,
                                 i_dc=x.get("i_op"), i_powerup=x.get("i_end"), findings=None))
    matches, unmatched = [], []
    for m in symptom["measured"]:
        best = []
        for c in contexts:
            for how in ("dc", "powerup"):
                s = c[how]
                if s is None or abs(s - m) > _tol(m):
                    continue
                # a power-up state only explains the reading when the DC answer under the same load does not
                if how == "powerup" and c["dc"] is not None and abs(c["dc"] - m) <= _tol(m):
                    continue
                best.append(dict(measured=m, how=how, load=c["load"], corner=c["corner"], temp=c["temp"],
                                 simulated=s, off=abs(s - m)))
        if best:
            matches += sorted(best, key=lambda b: b["off"])[:6]
        else:
            unmatched.append(m)
    return dict(ok=True, node=node, contexts=contexts, matches=matches, unmatched=unmatched,
                errors=[c["error"] for c in contexts if c["error"]])


def _node(nodes, name):
    for k, v in (nodes or {}).items():
        if k.lower() == name.lower():
            return v
    return None


def explain(res):
    """Plain sentences for a search result: one per measured value."""
    out = []
    for m in sorted({x["measured"] for x in res["matches"]} | set(res["unmatched"])):
        hits = [x for x in res["matches"] if x["measured"] == m]
        if not hits:
            out.append(f"{m:.3f} V: not reproduced by any load, corner or power-up tried.")
            continue
        load = lambda x: "no load" if x["load"] is None else f"a {_ohm(x['load'])} load"
        dc = [x for x in hits if x["how"] == "dc"]
        pu = [x for x in hits if x["how"] == "powerup"]
        if dc:
            x = dc[0]
            why = ("the block's working state" if x["load"] is None else
                   "the reading is set by what is connected (the unloaded answer differs)")
            out.append(f"{m:.3f} V: reproduced by the DC answer with {load(x)} ({x['simulated']:.3f} V at {x['corner']}, "
                       f"{x['temp']} °C; {len(dc)} matching context(s)): {why}.")
        if pu:
            x = pu[0]
            out.append(f"{m:.3f} V: reproduced by a power-up from 0 V with {load(x)} ({x['simulated']:.3f} V at "
                       f"{x['corner']}, {x['temp']} °C), where the DC answer is different: the chip came up in "
                       f"another operating point.")
    return out


def _ohm(r):
    return f"{r / 1e6:g} MΩ" if r >= 1e6 else f"{r / 1e3:g} kΩ"

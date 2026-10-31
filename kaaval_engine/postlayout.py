"""postlayout.py — the circuit as drawn against the circuit as simulated.

When a cell's layout matches its schematic device for device (layout_check), the two still differ in what the layout
adds: the capacitance of every wire, junction and overlap. Magic extracts the layout again with those capacitances
(extract.cell(parasitics=True)) and the review re-runs the very test it ran on the schematic (the same plan: supplies,
loads, conditions) on that post-layout netlist. Where the results disagree, the drawn chip behaves differently from
the simulated one: it comes up in another state, rests at another current, or its loop has less margin.

Wire resistance is not extracted (ext2spice cthresh 0, extresist off), so the comparison covers capacitive effects
only, and says so.

    cell = post_cell(name)                 # the post-layout netlist's cell name in a review's files
    diffs = compare(kind, schematic_rows, layout_rows)
"""
OUT = "kaaval_extracted"
CURRENT = 0.25          # settled supply current differing by more than 25 % (and 0.1 uA)
VOLTS = 0.1             # a node resting more than 100 mV apart
PM = 10.0               # phase margin more than 10 degrees apart
UGF = 0.25              # unity-gain frequency more than 25 % apart


def post_path(cell):
    return f"{OUT}/{cell}.post.spice"


def post_cell(cell):
    return f"{post_path(cell)}#{cell}"


def _key(r):
    return (r.get("case"), r.get("corner"), r.get("temp"), r.get("vscale"))


def _state(r):
    """dead / oscillates / settled, as checks.state, from a stored result row."""
    if r.get("state"):
        return r["state"]
    if (r.get("i_op") or 0) > 1e-7 and abs(r.get("i_end") or 0) < 0.2 * r["i_op"]:
        return "dead"
    return "oscillates" if r.get("swing") else "settled"


def compare(kind, sch, lay):
    """[{cond, what, schematic, layout}] for every condition where both views completed and disagree."""
    a = {_key(r): r for r in sch if not r.get("error")}
    b = {_key(r): r for r in lay if not r.get("error")}
    out = []
    for k in sorted(set(a) & set(b), key=str):
        x, y = a[k], b[k]
        cond = [v for v in k[1:]]
        if kind in ("powerup", "sequence"):
            if _state(x) != _state(y):
                out.append(dict(cond=cond, what="state", schematic=_state(x), layout=_state(y), case=k[0]))
                continue
            i0, i1 = abs(x.get("i_end") or 0), abs(y.get("i_end") or 0)
            if abs(i0 - i1) > max(CURRENT * max(i0, i1), 1e-7):
                out.append(dict(cond=cond, what="supply current", schematic=i0, layout=i1, case=k[0]))
                continue
            nx, ny = x.get("nodes") or {}, y.get("nodes") or {}
            common = [n for n in nx if n in ny and nx[n][1] is not None and ny[n][1] is not None]
            worst = max(common, key=lambda n: abs(nx[n][1] - ny[n][1]), default=None)
            if worst and abs(nx[worst][1] - ny[worst][1]) > VOLTS:
                out.append(dict(cond=cond, what=f"{worst} after power-up", schematic=nx[worst][1],
                                layout=ny[worst][1], case=k[0]))
        elif kind == "stability":
            if x.get("pm") is not None and y.get("pm") is not None and abs(x["pm"] - y["pm"]) > PM:
                out.append(dict(cond=cond, what="phase margin", schematic=x["pm"], layout=y["pm"]))
            elif x.get("ugf") and y.get("ugf") and abs(x["ugf"] - y["ugf"]) > UGF * max(x["ugf"], y["ugf"]):
                out.append(dict(cond=cond, what="unity-gain frequency", schematic=x["ugf"], layout=y["ugf"]))
    return out


def _fmt(what, v):
    if what == "supply current":
        return f"{v * 1e6:.3g} µA"
    if what == "phase margin":
        return f"{v:.0f}°"
    if what == "unity-gain frequency":
        return f"{v / 1e6:.3g} MHz"
    return f"{v:.3f} V" if isinstance(v, (int, float)) else str(v)


def finding(cell, kind, diffs, n):
    """A review finding for a cell whose post-layout netlist behaves differently, or None."""
    if not diffs:
        return None
    order = {"state": 0, "phase margin": 1, "supply current": 2}
    d = min(diffs, key=lambda d: order.get(d["what"], 3))
    c = d["cond"]
    return dict(rule="layout/post_layout_differs", severity="warn", device=cell,
                title=(f"{cell}: with the capacitance its layout adds, the {kind} test gives another result at "
                       f"{len(diffs)}/{n} conditions: {d['what']} {_fmt(d['what'], d['schematic'])} in the schematic, "
                       f"{_fmt(d['what'], d['layout'])} as drawn (at {c[0]}, {c[1]} °C, supply x{c[2]}). Extracted "
                       f"wire and junction capacitance only; wire resistance is not included.")[:700],
                detail=dict(diffs=diffs[:40], kind=kind, n=n))

"""checks.py — analog design checks over a PVT sweep of a repo's testbench (operating point level).

pvt_sweep runs the testbench's DC operating point at every (process corner, temperature, supply scale) and keeps each
transistor's region, current and saturation margin (|Vds| - |Vdsat|). Two checks read the sweep:

  headroom  a device in saturation at nominal (tt, 27 C, nominal supply) that drops into triode at some condition:
            the classic mirror / cascode / tail-source failure at a corner. Reported with the worst condition.
  bias      a device carrying real current at nominal (> 100 nA) whose current falls below 20 % of it somewhere:
            a bias or reference that does not start, or collapses, at that condition.

Both are statements about the circuit as simulated with the open PDK models, not about silicon.
"""
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed

from kaaval_engine import sim

CORNERS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40, 27, 125]
VSCALES = [0.9, 1.0, 1.1]
NOMINAL = ("tt", 27, 1.0)


def pvt_sweep(tb, corners=CORNERS, temps=TEMPS, vscales=VSCALES, workers=2, on_result=None, known=None):
    """{(corner, temp, vscale): (ops, err)}; on_result(cond, ops, err) is called as results land, so a UI can show
    the sweep filling in. `known` holds conditions already simulated (e.g. the nominal point).

    One ngspice session per process corner (sim.op_points_corner): the PDK library loads once and temperature and
    supply are stepped inside it, ~9x faster than a session per condition with identical results."""
    conds = list(itertools.product(corners, temps, vscales))
    out = dict(known or {})
    by_corner = {}
    for c in conds:
        if c not in out:
            by_corner.setdefault(c[0], []).append((c[1], c[2]))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(sim.op_points_corner, tb, k, tv): k for k, tv in by_corner.items()}
        for f in as_completed(futs):
            k = futs[f]
            for (t, v), r in f.result().items():
                out[(k, t, v)] = r
                if on_result:
                    on_result((k, t, v), *r)
    return {c: out[c] for c in conds}


def circuit_kind(tb):
    """'static' when the designer judges the circuit at a resting bias point (their testbench runs .op, .dc or .ac),
    'dynamic' when they only ever run it in time (.tran only): oscillators, charge pumps, comparators, switched
    circuits. A DC operating point of a dynamic circuit can be an unstable balance it never sits at on the chip, so the
    headroom and bias checks are not applied to it. With no analyses found, the circuit is treated as static."""
    kinds = {a.split()[0].lstrip(".").lower() for a in tb.analyses if a.split()}
    if kinds and kinds <= {"tran"}:
        return dict(kind="dynamic", reason="the designer's testbench only runs transient analysis, so the circuit is "
                                            "meant to be judged while it switches, not at a resting bias point")
    return dict(kind="static", reason="the designer's testbench analyses its bias point (" +
                (", ".join(sorted(kinds - {"tran"})) or "no analysis named") + ")")


def margin(d):
    return abs(d.get("vds", 0.0)) - abs(d.get("vdsat", 0.0))


def headroom(sweep, min_margin=0.0):
    nom, err = sweep[NOMINAL]
    if err or not nom:
        return []
    out = []
    for dev, d0 in nom.items():
        if d0["region"] != "sat":
            continue
        bad = [(c, ops[dev]) for c, (ops, e) in sweep.items() if not e and ops and dev in ops
               and ops[dev]["region"] == "triode"]
        if not bad:
            continue
        worst_c, worst = min(bad, key=lambda x: margin(x[1]))
        out.append(dict(rule="analog/headroom", severity="warn", device=dev,
                        nominal_margin=margin(d0), worst_margin=margin(worst), worst=worst_c,
                        n_bad=len(bad), n=len(sweep),
                        message=f"{dev} is in saturation at nominal (margin {margin(d0) * 1e3:.0f} mV) but in triode "
                                f"at {len(bad)}/{len(sweep)} PVT conditions; worst {worst_c[0]}, {worst_c[1]} °C, "
                                f"supply ×{worst_c[2]}: Vds {abs(worst.get('vds', 0)):.3f} V < Vdsat "
                                f"{abs(worst.get('vdsat', 0)):.3f} V"))
    return out


def bias(sweep, floor=1e-7, frac=0.2, share=0.3):
    nom, err = sweep[NOMINAL]
    if err or not nom:
        return []
    # a start-up leg is meant to switch off once its reference runs: only devices carrying a real share of their own
    # block's current (>= `share` x the block's median) can "collapse"
    blocks = {}
    for dev, d0 in nom.items():
        blocks.setdefault(dev.rsplit(".", 1)[0], []).append(abs(d0.get("id", 0.0)))
    med = {b: sorted(v)[len(v) // 2] for b, v in blocks.items()}
    out = []
    for dev, d0 in nom.items():
        i0 = abs(d0.get("id", 0.0))
        if i0 < floor or i0 < share * med[dev.rsplit(".", 1)[0]]:
            continue
        low = [(c, abs(ops[dev].get("id", 0.0))) for c, (ops, e) in sweep.items()
               if not e and ops and dev in ops and abs(ops[dev].get("id", 0.0)) < frac * i0]
        if not low:
            continue
        wc, wi = min(low, key=lambda x: x[1])
        out.append(dict(rule="analog/bias_collapse", severity="warn", device=dev, nominal_id=i0, worst_id=wi,
                        worst=wc, n_bad=len(low), n=len(sweep),
                        message=f"{dev} carries {i0:.3g} A at nominal but below {frac:.0%} of it at {len(low)}/"
                                f"{len(sweep)} conditions; worst {wc[0]}, {wc[1]} °C, supply ×{wc[2]}: {wi:.3g} A"))
    return out


def failures(sweep):
    return [(c, e) for c, (ops, e) in sweep.items() if e]


# ---------------------------------------------------------------- switching circuits
def function_loss(tsweep, min_frac=0.3, level_tol=0.25):
    """Findings for a switching circuit from its transient sweep {(corner, temp, vscale): ({net: meas}, err)}.

    Per output net, the nominal behaviour sets the test: an output that toggles at nominal (swing over min_frac of the
    supply) must keep toggling; a steady output must stay within level_tol of its nominal level. Also reports the
    spread of frequency / level across every condition that simulated, for the bench."""
    nom, err = tsweep.get(NOMINAL, (None, "missing"))
    if err or not nom:
        return [], {}
    vdd = max((abs(m["mean"]) + m["pp"] / 2 for m in nom.values()), default=1.8) or 1.8
    out, spread = [], {}
    for net, m0 in nom.items():
        toggles = m0["pp"] > min_frac * vdd and m0["freq"] > 0
        vals = [(c, r[0][net]) for c, r in tsweep.items() if not r[1] and r[0] and net in r[0]]
        if toggles:
            fs = [v["freq"] for _, v in vals if v["freq"] > 0]
            spread[net] = dict(kind="toggle", nominal=m0["freq"], lo=min(fs, default=0), hi=max(fs, default=0))
            dead = [(c, v) for c, v in vals if not (v["pp"] > min_frac * m0["pp"] and v["freq"] > 0)]
            if dead:
                wc, wv = min(dead, key=lambda x: x[1]["pp"])
                out.append(dict(rule="analog/stops_switching", severity="warn", device=net, worst=wc, n_bad=len(dead),
                                n=len(tsweep), message=f"{net} toggles at nominal ({m0['freq'] / 1e6:.3g} MHz, "
                                f"{m0['pp']:.2f} V swing) but stops switching at {len(dead)}/{len(tsweep)} PVT "
                                f"conditions; worst {wc[0]}, {wc[1]} °C, supply ×{wc[2]}: swing {wv['pp']:.3f} V"))
        else:
            lv = [v["mean"] for _, v in vals]
            spread[net] = dict(kind="level", nominal=m0["mean"], lo=min(lv, default=0), hi=max(lv, default=0))
            ref = max(abs(m0["mean"]), 0.1)
            off = [(c, v) for c, v in vals if abs(v["mean"] - m0["mean"]) > level_tol * ref]
            if off:
                wc, wv = max(off, key=lambda x: abs(x[1]["mean"] - m0["mean"]))
                # a level that follows supply / temperature is not a defect by itself: without the designer's spec it
                # is reported as information, never as a risk
                lo, hi = min(v["mean"] for _, v in vals), max(v["mean"] for _, v in vals)
                out.append(dict(rule="analog/level_spread", severity="info", device=net, worst=wc, n_bad=len(off),
                                n=len(tsweep), message=f"{net} is {m0['mean']:.3f} V at nominal and ranges "
                                f"{lo:.3f}–{hi:.3f} V across PVT ({len(off)}/{len(tsweep)} conditions move it more than "
                                f"{level_tol:.0%}); whether that is acceptable depends on the design's spec"))
    return out, spread


# ---------------------------------------------------------------- start-up
SU_TEMPS = TEMPS
SU_VSCALES = [0.9, 1.0]


def startup(ssweep, vtol=0.1):
    """Power-up findings from sim.startup_corner results {(corner, temp, vscale): (result, err)}.

    At each condition the circuit is powered up from 0 V and held with constant sources, then compared with the
    operating point a DC analysis reports:
      oscillates   a node still swings more than 50 mV at the end: the circuit never rests at its operating point
                   (an unstable loop), whatever its DC analysis says.
      two states   every node has settled, nothing swings, and some node sits more than `vtol` from the DC answer.
                   A settled circuit under constant sources is itself a DC solution, so the circuit has two operating
                   points and can come up in either; both are reported with their supply currents.
    A node still drifting at the end proves nothing and is not reported."""
    osc, two, dead = [], [], []
    for c, (r, e) in ssweep.items():
        if e or not r:
            continue
        # the supply current settled near zero while the DC analysis reports a working bias: the circuit stays off.
        # Nodes of a dead circuit float on leakage, so their drift says nothing; the steady supply current decides
        if r["i_op"] > 1e-7 and r["i_end"] < 0.2 * r["i_op"] and \
                abs(r["i_end"] - r.get("i_prev", r["i_end"])) < 0.05 * r["i_op"]:
            dead.append((c, r))
            continue
        if r.get("swing"):
            n, pp = max(r["swing"].items(), key=lambda x: x[1])
            osc.append((c, n, pp, r))
            continue
        if r.get("moving"):
            continue
        if not r.get("confirmed"):
            continue
        diffs = [(n, a, b) for n, (a, b) in r["nodes"].items() if a is not None and b is not None and abs(a - b) > vtol]
        if diffs:
            two.append((c, max(diffs, key=lambda x: abs(x[1] - x[2])), r))
    n = len([1 for r, e in ssweep.values() if not e and r])
    out = []
    if dead:
        c, r = min(dead, key=lambda x: x[1]["i_end"] / x[1]["i_op"])
        out.append(dict(rule="analog/no_startup", severity="warn", device="supply", worst=c, n_bad=len(dead), n=n,
                        conds=[list(x[0]) for x in dead], states=[dict(i=r["i_op"]), dict(i=r["i_end"])],
                        message=f"Powered up from 0 V, the circuit stays off at {len(dead)}/{n} conditions: the "
                                f"supply current settles at {r['i_end'] * 1e9:.2f} nA while its DC analysis reports a "
                                f"working bias of {r['i_op'] * 1e6:.1f} µA (worst {c[0]}, {c[1]} °C, supply ×{c[2]}; "
                                f"ramp {r['ramp'] * 1e6:.0f} µs, held {r['settle'] * 1e6:.0f} µs). The zero-current "
                                f"state is a valid solution and nothing pushes the circuit out of it: it needs a "
                                f"start-up circuit."))
    if osc:
        c, node, pp, r = max(osc, key=lambda x: x[2])
        out.append(dict(rule="analog/oscillates", severity="warn", device=node, worst=c, n_bad=len(osc), n=n,
                        conds=[list(x[0]) for x in osc],
                        message=f"After power-up the circuit never settles: {node} keeps swinging {pp * 1e3:.0f} mV "
                                f"peak-to-peak at {len(osc)}/{n} conditions (worst {c[0]}, {c[1]} °C, supply ×{c[2]}). "
                                f"The operating point its DC analysis reports is not where it rests: a loop is "
                                f"unstable."))
    if two:
        c, (node, a, b), r = max(two, key=lambda x: abs(x[1][1] - x[1][2]))
        out.append(dict(rule="analog/two_states", severity="warn", device=node, worst=c, n_bad=len(two), n=n,
                        conds=[list(x[0]) for x in two], states=[dict(v=a, i=r["i_op"]), dict(v=b, i=r["i_end"])],
                        message=f"The circuit has two operating points at {len(two)}/{n} conditions: at {c[0]}, "
                                f"{c[1]} °C, supply ×{c[2]}, {node} rests at {a:.3f} V ({r['i_op'] * 1e6:.1f} µA "
                                f"from the supply) in the DC analysis and at {b:.3f} V ({r['i_end'] * 1e6:.1f} µA) "
                                f"after a power-up from 0 V, both settled. A reference or bias block must have one "
                                f"state, so a start-up circuit has to rule the other out; a latch, comparator with "
                                f"hysteresis or flip-flop is meant to have two."))
    return out


# ---------------------------------------------------------------- stability
def stability(lsweep, pm_min=45.0, gm_min=6.0):
    """Findings from loop-gain results {(corner, temp, vscale): (margins, err)} (sim.loopgain_corner).

      unstable          phase margin below 0 or gain margin below 0 dB, or positive feedback at DC: the loop
                        oscillates or latches at that condition.
      low_phase_margin  phase margin below `pm_min` (45 deg) or gain margin below `gm_min` (6 dB): the loop rings and
                        is sensitive to load and process. Phase margin about 45 deg gives ~20 % step overshoot; 20 deg
                        gives ~45-50 % (checked on our own two-stage op-amp, tests/test_kaaval_stability.py).
    Each is reported once with every failing condition and the worst one."""
    ok = {c: r for c, (r, e) in lsweep.items() if not e and r}
    n = len(ok)
    bad, low = [], []
    for c, r in ok.items():
        pm, gm = r.get("pm"), r.get("gm_db")
        if r.get("positive_dc") or (pm is not None and pm < 0) or (gm is not None and gm < 0):
            bad.append((c, r))
        elif (pm is not None and pm < pm_min) or (gm is not None and gm < gm_min):
            low.append((c, r))
    fmt = lambda r: (f"phase margin {r['pm']:.0f}°" if r.get("pm") is not None else "no unity-gain crossing") + \
        (f", gain margin {r['gm_db']:.1f} dB" if r.get("gm_db") is not None else "") + \
        (f", unity gain at {r['ugf'] / 1e6:.3g} MHz" if r.get("ugf") else "")
    pms = [r["pm"] for r in ok.values() if r.get("pm") is not None]
    span = f" Across the conditions that simulated the phase margin spans {min(pms):.0f}–{max(pms):.0f}°." if pms else ""
    out = []
    if bad:
        c, r = min(bad, key=lambda x: x[1].get("pm") if x[1].get("pm") is not None else -999)
        out.append(dict(rule="analog/unstable", severity="warn", device="loop", worst=c, n_bad=len(bad), n=n,
                        conds=[list(x[0]) for x in bad], margins=r,
                        message=f"The loop is unstable at {len(bad)}/{n} conditions: worst {c[0]}, {c[1]} °C, supply "
                                f"×{c[2]}: " + ("positive feedback at DC" if r.get("positive_dc") else fmt(r)) +
                                ". It will oscillate or latch there." + span))
    if low:
        c, r = min(low, key=lambda x: x[1].get("pm") if x[1].get("pm") is not None else 999)
        out.append(dict(rule="analog/low_phase_margin", severity="warn", device="loop", worst=c, n_bad=len(low), n=n,
                        conds=[list(x[0]) for x in low], margins=r,
                        message=f"The loop has thin margins at {len(low)}/{n} conditions (below {pm_min:.0f}° phase "
                                f"or {gm_min:.0f} dB gain margin): worst {c[0]}, {c[1]} °C, supply ×{c[2]}: {fmt(r)}. "
                                f"Expect ringing on steps and sensitivity to load." + span))
    return out


# ---------------------------------------------------------------- power-up sequence
def state(r):
    """How one power-up ended: dead (supply current settled near zero against a working DC bias), oscillates,
    unresolved (still moving) or settled."""
    if r["i_op"] > 1e-7 and r["i_end"] < 0.2 * r["i_op"] and \
            abs(r["i_end"] - r.get("i_prev", r["i_end"])) < 0.05 * r["i_op"]:
        return "dead"
    if r.get("swing"):
        return "oscillates"
    return "unresolved" if r.get("moving") else "settled"


def sequence(per, meta=None, vtol=0.1):
    """Findings from a sequence test {case: {(corner, temp, vscale): (result, err)}}; the first case is the reference
    (every rail together, fast). A block on a chip must come up the same way however its rails, enables and resets
    arrive, so every case is compared with the reference at the same condition:
      sequence_dependent   at some condition a case ends dead, oscillating, or settled in a different state (a node
                           more than `vtol` away) while the reference came up working - the block depends on how the
                           chip powers up.
    The reference's own power-up findings (checks.startup) are reported too, marked with the case. With `meta` (see
    plan.cases) the finding also states, for the failing rail order, the smallest gap between the rails that fails
    and the largest that passes, so it never rests on one chosen gap."""
    meta = meta or {}
    names = list(per)
    ref = per[names[0]]
    out = [dict(f, case=names[0]) for f in startup(ref)]
    bad = []
    for name in names[1:]:
        for c, (r, e) in per[name].items():
            r0, e0 = ref.get(c, (None, "missing"))
            if e or e0 or not r or not r0 or state(r0) != "settled":
                continue
            s = state(r)
            if s in ("dead", "oscillates"):
                bad.append((name, c, s, None, r, r0))
            elif s == "settled":
                diffs = [(n, r0["nodes"][n][1], b) for n, (a, b) in r["nodes"].items()
                         if n in r0["nodes"] and b is not None and r0["nodes"][n][1] is not None
                         and abs(b - r0["nodes"][n][1]) > vtol]
                if diffs:
                    bad.append((name, c, "other state", max(diffs, key=lambda x: abs(x[1] - x[2])), r, r0))
    if bad:
        def weight(x):
            return 2.0 if x[2] == "dead" else 1.5 if x[2] == "oscillates" else abs(x[3][1] - x[3][2])
        name, c, s, d, r, r0 = max(bad, key=weight)
        n = sum(1 for sw in per.values() for r_, e_ in sw.values() if r_ and not e_)
        cases_bad = list(dict.fromkeys(x[0] for x in bad))
        what = (f"stays off: supply current {r['i_end'] * 1e9:.2f} nA instead of {r0['i_end'] * 1e6:.1f} µA" if s == "dead"
                else f"never settles: {max(r['swing'], key=r['swing'].get)} keeps swinging" if s == "oscillates"
                else f"lands in another state: {d[0]} at {d[2]:.3f} V instead of {d[1]:.3f} V")
        gaps, m = "", meta.get(name)
        if m and m.get("lead"):
            same = [k for k, x in meta.items() if x["lead"] == m["lead"] and x["speed"] == m["speed"]
                    and x["late"] == m["late"]]
            failing = {meta[x[0]]["gap"] for x in bad if x[0] in same}
            fail_min = min(failing)
            passing = [meta[k]["gap"] for k in same if meta[k]["gap"] not in failing and meta[k]["gap"] < fail_min]
            gaps = (f" It fails once {m['lead']} leads by {fail_min * 1e6:.0f} µs or more" +
                    (f" and passes at {max(passing) * 1e6:.0f} µs" if passing else " (the shortest gap tried)") + ".")
            m = dict(m, fail_gap=fail_min, pass_gap=max(passing) if passing else None)
        out.append(dict(rule="analog/sequence_dependent", severity="warn", device=(d[0] if d else "supply"), worst=c,
                        case=name, cases=cases_bad, n_bad=len(bad), n=n, sequence=m,
                        conds=[[x[0], *x[1]] for x in bad],
                        message=f"The block comes up differently depending on how the chip powers up: with {name} it "
                                f"{what} (at {c[0]}, {c[1]} °C, supply ×{c[2]}), while with every rail together and "
                                f"fast it comes up working. {len(bad)} of {n} power-ups differ, in "
                                f"{len(cases_bad)} sequence(s): {'; '.join(cases_bad[:4])}.{gaps} On a real chip the rails, "
                                f"enables and resets arrive in an order and at a speed the block does not choose."))
    return out

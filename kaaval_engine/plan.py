"""plan.py — run a reviewer's test plan: tests the designer never wrote, compiled by us, never raw SPICE.

A plan names a cell (a schematic in the workspace), how to power it (which ports are supplies at what voltage, which
are ground), optional loads on its ports, and the analysis to run across process, temperature and supply. The plan is
data, checked against the circuit before anything runs: the cell must exist inside the workspace, every port must be a
net of that cell, values must be physical, and only known test kinds are accepted. The engine builds the deck itself
from the cell's own netlist (kaaval_engine.netlist) and the trimmed PDK, so a planner (Muse Spark, or any other) can
choose WHAT to test but cannot inject simulator commands.

    stability plan: {"cell", "kind": "stability", "supplies", "grounds", "biases": [{"port", "volts"}],
                     "ties": [{"a", "b", "ohms"}] (resistors between ports, element Rtie<i>, pin 1 on a),
                     "loads": [{"port", "farads"} | {"port", "ohms"}], "break": {"net", "pins": ["XM1.g"]}, PVT...}
    The loop is cut on `net`, with the listed element pins on one side; loop gain T(f) by Tian's method gives
    unity-gain frequency, phase margin and gain margin at every condition (sim.loopgain_corner).

    sequence plan: a powerup plan plus "controls": [{"port", "volts"}] (enables, resets: element Vctl<i>). The engine
    powers the cell up in every case of cases(): rails together or each rail first (the others 10 µs, 100 µs or 1 ms
    later), fast (2 µs) or slow (1 ms) ramps,
    controls rising with the rails or released after them; the cell must end in the same state in every case
    (checks.sequence).
    domains plan: a powerup plan whose cell has several supplies. Every MOSFET's operating point is solved with all rails
    on and with each rail off while the others are up (the chip part-way through power-up), and each device's voltages
    are judged against its sky130 rating (checks.overstress): a 1.8 V device reached by a 3.3 V node.
    A control may carry "wave": [[t, 0|1], ...], its timing as the project's own logic drives it
    (from a digital simulation, kaaval_engine.vcd), t in seconds after the rails are up: each rail order and speed
    then also runs with every waved control following its wave. Any plan may list "pads": [{"port"}]: that port drives the Tiny Tapeout pad path (PAD).

    plan = {"cell": "xschem/core_prel.sch", "kind": "powerup",
            "supplies": {"VDD": 1.8}, "grounds": ["VSS"], "loads": [{"port": "Vbgr", "ohms": 1e7}],
            "corners": ["tt", "ss"], "temps": [-40, 27], "vscales": [0.9, 1.0],
            "why": "self-biased bandgap core with no visible start-up path"}
    errors = validate(plan, root)          # [] when the plan can run
    result = run(plan, root)               # findings + per-condition results
"""
import os, re, time

from kaaval_engine import checks, sim, spice_cells, vcd
from kaaval_engine import netlist as N

KINDS = {"powerup", "stability", "sequence", "domains", "drive"}
MAX_CONDS = 45
MAX_RUNS = 128                    # sequence tests: cases x conditions, each one power-up transient
# the Tiny Tapeout analog pad path (tinytapeout.com/specs/analog): under 500 ohm and 5 pF from the macro pin to the pad
# through the analog switch. Whatever is on the board is not modelled here: TT's demo-board guide says the stock analog
# pull-downs (value unpublished) load outputs too heavily and should be removed or be at least 1 Mohm (BOARD_MIN); the
# drive test sweeps the load instead of assuming one.
PAD = dict(ohms=500.0, farads=5e-12)
BOARD_MIN = 1e6
DRIVE_LOADS = [1e7, BOARD_MIN, 1e5, 1e4]          # resistive loads on a pad (ohm), after the unloaded case
FAST, SLOW = 2e-6, 1e-3          # rail ramp times
# a second rail arrives some time after the first is up; no one gap is right for every chip (it depends on the board's
# regulators), so the gap is swept and a finding reports the smallest gap that fails and the largest that passes
GAPS = [10e-6, 100e-6, 1e-3]
LATE = 20e-6                      # enables / resets released LATE after the rails
HELD = (0.0, 0.5, 1.0)            # an oscillation found with inputs undriven is re-run with them held at these
                                  # fractions of the highest supply
HELD_LONGER = 4                   # a held level still moving at the end is held this many times longer, once
HELD_BUDGET = 120.0               # seconds for those re-runs, on top of the test's own share of the review's budget
WAVE_MAX_T = 5e-3                 # a control's logic wave covers at most the first 5 ms after the rails
SEQ_CORNERS, SEQ_TEMPS, SEQ_VSCALES = ["tt", "ss", "ff"], [-40, 27, 125], [1.0]


def _nets(circuit):
    """Every net name in a flat netlist (pins of top-level elements)."""
    nets = set()
    depth = 0
    for line in circuit.splitlines():
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
            continue
        if low.startswith(".ends"):
            depth -= 1
            continue
        if depth or not low or low[0] in "*.+":
            continue
        p = re.sub(r"'[^']*'|\{[^}]*\}", "", line).split()
        t = p[0][0].lower()
        if t == "x":
            nets.update(w for w in p[1:-1] if "=" not in w)
        elif t == "m":
            nets.update(p[1:5])
        elif t in "rcldvieq":
            nets.update(p[1:3])
    return nets


def _cell_circuit(plan, root):
    """The cell's own netlist: an xschem schematic netlisted by us, or a SPICE subcircuit ("<file>#<NAME>")."""
    rel = str(plan.get("cell", ""))
    if "#" in rel:
        circ, _ = spice_cells.load(root, rel)
        return circ
    p = _cell(plan, root)
    return N.netlist(p) if p else None


def _cell(plan, root):
    rel = str(plan.get("cell", ""))
    if "#" in rel:
        f = os.path.realpath(os.path.join(root, rel.split("#")[0]))
        return f if f.startswith(os.path.realpath(root) + os.sep) and os.path.isfile(f) else None
    p = os.path.realpath(os.path.join(root, rel))
    if not rel or not p.startswith(os.path.realpath(root) + os.sep) or not p.endswith(".sch") or not os.path.isfile(p):
        return None
    return p


def validate(plan, root):
    """List of problems (empty when the plan can run). Every name is checked against the cell's own netlist."""
    err = []
    if plan.get("kind") not in KINDS:
        err.append(f"unknown test kind {plan.get('kind')!r} (known: {', '.join(sorted(KINDS))})")
    p = _cell(plan, root)
    if not p:
        return err + [f"cell {plan.get('cell')!r} is not a schematic or SPICE subcircuit in this repository"]
    try:
        circ0 = _cell_circuit(plan, root)
        if not circ0:
            return err + [f"cell {plan.get('cell')!r}: no such subcircuit in that file"]
        nets = {n.lower(): n for n in _nets(circ0)}
    except Exception as e:                                   # noqa: BLE001 - a broken schematic is a plan error
        return err + [f"cell {plan['cell']} could not be read: {e}"]
    sup = plan.get("supplies") or {}
    if not sup:
        err.append("no supply: name at least one port and its voltage")
    for port, v in sup.items():
        if port.lower() not in nets:
            err.append(f"supply port {port!r} is not a net of {plan['cell']}")
        if not isinstance(v, (int, float)) or not 0.3 <= v <= 6.0:
            err.append(f"supply {port}={v!r} V is outside 0.3–6 V")
    for g in plan.get("grounds") or []:
        if g.lower() not in nets:
            err.append(f"ground port {g!r} is not a net of {plan['cell']}")
    for ld in plan.get("loads") or []:
        if str(ld.get("port", "")).lower() not in nets:
            err.append(f"load port {ld.get('port')!r} is not a net of {plan['cell']}")
        if "farads" in ld:
            c = ld.get("farads")
            if not isinstance(c, (int, float)) or not 1e-18 <= c <= 1e-6:
                err.append(f"load {ld.get('port')} {c!r} F is outside 1 aF–1 µF")
        else:
            r = ld.get("ohms")
            if not isinstance(r, (int, float)) or not 1.0 <= r <= 1e10:
                err.append(f"load {ld.get('port')} {r!r} Ω is outside 1 Ω–10 GΩ")
    for b in plan.get("biases") or []:
        if str(b.get("port", "")).lower() not in nets:
            err.append(f"bias port {b.get('port')!r} is not a net of {plan['cell']}")
        if not isinstance(b.get("volts"), (int, float)) or not -1.0 <= b["volts"] <= 6.0:
            err.append(f"bias {b.get('port')}={b.get('volts')!r} V is outside -1…6 V")
    for i, t in enumerate(plan.get("ties") or []):
        for k in ("a", "b"):
            if str(t.get(k, "")).lower() not in nets:
                err.append(f"tie {i} port {t.get(k)!r} is not a net of {plan['cell']}")
        if not isinstance(t.get("ohms"), (int, float)) or not 1e-3 <= t["ohms"] <= 1e10:
            err.append(f"tie {i} {t.get('ohms')!r} Ω is outside 1 mΩ–10 GΩ")
    for c in plan.get("controls") or []:
        if str(c.get("port", "")).lower() not in nets:
            err.append(f"control port {c.get('port')!r} is not a net of {plan['cell']}")
        if not isinstance(c.get("volts"), (int, float)) or not 0.0 <= c["volts"] <= 6.0:
            err.append(f"control {c.get('port')}={c.get('volts')!r} V is outside 0…6 V")
        if "wave" in c:
            w = c["wave"]
            ok = isinstance(w, list) and 0 < len(w) <= vcd.MAX_EDGES and all(
                isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[0], (int, float)) and
                0 <= x[0] <= WAVE_MAX_T and x[1] in (0, 1) for x in w)
            if not ok or any(b[0] < a[0] for a, b in zip(w, w[1:])):
                err.append(f"control {c.get('port')} wave must be 1-{vcd.MAX_EDGES} [t, 0|1] pairs in time order, "
                           f"0 <= t <= {WAVE_MAX_T * 1e3:.0f} ms")
    for pd in plan.get("pads") or []:
        if str(pd.get("port", "")).lower() not in nets:
            err.append(f"pad port {pd.get('port')!r} is not a net of {plan['cell']}")
    if plan.get("kind") == "drive" and not plan.get("pads"):
        err.append("a drive test needs at least one pad port (an output that leaves the chip)")
    if plan.get("kind") == "stability":
        br = plan.get("break") or {}
        if str(br.get("net", "")).lower() not in nets:
            err.append(f"break net {br.get('net')!r} is not a net of {plan['cell']}")
        elif not br.get("pins"):
            err.append("break needs the element pins on one side of the cut, e.g. ['XM1.g']")
        else:
            if not err:
                try:
                    sim.break_net(compile_bench(plan, root).circuit, nets[br["net"].lower()], br["pins"])
                except ValueError as e:
                    err.append(f"break: {e}")
    corners, temps, vscales = _pvt(plan)
    if not set(corners) <= set(checks.CORNERS):
        err.append(f"corners must be among {checks.CORNERS}")
    if not all(isinstance(t, (int, float)) and -55 <= t <= 150 for t in temps):
        err.append("temperatures must be within -55…150 °C")
    if not all(isinstance(v, (int, float)) and 0.7 <= v <= 1.3 for v in vscales):
        err.append("supply scales must be within 0.7…1.3")
    if len(corners) * len(temps) * len(vscales) > MAX_CONDS:
        err.append(f"at most {MAX_CONDS} conditions per test")
    if plan.get("kind") == "sequence" and not err and \
            len(cases(plan)) * len(corners) * len(temps) * len(vscales) > MAX_RUNS:
        err.append(f"at most {MAX_RUNS} power-ups per sequence test: name fewer conditions")
    return err


def _pvt(plan):
    seq = plan.get("kind") == "sequence"
    return (plan.get("corners") or (SEQ_CORNERS if seq else checks.CORNERS),
            plan.get("temps") or (SEQ_TEMPS if seq else checks.TEMPS),
            plan.get("vscales") or (SEQ_VSCALES if seq else checks.SU_VSCALES))


def cases(plan):
    """The power-up sequences of a sequence plan: [(name, schedule, meta)], the first (all together, fast) the
    reference. A schedule maps the bench's source names to (start, ramp), see sim._ramped; meta holds the case's
    order (None = together, else the rail that leads), speed, gap (s) and whether controls come late."""
    sup = [(f"vplan{i}", p) for i, p in enumerate(plan.get("supplies") or {})]
    ctl = [(f"vctl{i}", c["port"]) for i, c in enumerate(plan.get("controls") or [])]
    waves = {f"vctl{i}": c["wave"] for i, c in enumerate(plan.get("controls") or []) if c.get("wave")}
    orders = [(None, 0.0)] + ([(p, g) for _, p in sup for g in GAPS] if len(sup) > 1 else [])
    src = dict((p, s) for s, p in sup)
    out = []
    for speed, rr in (("fast", FAST), ("slow", SLOW)):
        for lead, gap in orders:
            sched = {s: ((0.0 if lead in (None, p) else rr + gap), rr) for s, p in sup}
            end = max(a + b for a, b in sched.values())
            for late in ([False, True] + (["logic"] if waves else []) if ctl else [False]):
                sc = dict(sched)
                for s, _ in ctl:
                    sc[s] = (("wave", [[end + t, b] for t, b in waves[s]]) if late == "logic" and s in waves else
                             (end + LATE, FAST) if late is True else (0.0, rr))
                oname = "together" if lead is None else f"{lead} first, others {gap * 1e6:.0f} µs later"
                how = ("as the project's logic drives them" if late == "logic" else
                       "after the rails" if late else "with the rails")
                name = f"rails {oname}, {speed} ({rr * 1e6:.0f} µs ramps)" + \
                    (f", {'/'.join(p for _, p in ctl)} {how}" if ctl else "")
                out.append((name, sc, dict(lead=lead, speed=speed, gap=gap, late=late)))
    assert not sup or all(src)
    return out


def compile_bench(plan, root):
    """The Testbench the plan describes: the cell's own netlist plus our sources and loads, nothing else."""
    p = _cell(plan, root)
    circ = _cell_circuit(plan, root)
    nets = {n.lower(): n for n in _nets(circ)}
    lines = [circ]
    for i, (port, v) in enumerate((plan.get("supplies") or {}).items()):
        lines.append(f"Vplan{i} {nets[port.lower()]} 0 {float(v):.6g}")
    for i, g in enumerate(plan.get("grounds") or []):
        lines.append(f"Vgnd{i} {nets[g.lower()]} 0 0")
    # ties: resistors between two ports (a feedback network); tie i is element Rtie<i>, pin 1 on a, pin 2 on b
    for i, t in enumerate(plan.get("ties") or []):
        lines.append(f"Rtie{i} {nets[t['a'].lower()]} {nets[t['b'].lower()]} {float(t['ohms']):.6g}")
    for i, b in enumerate(plan.get("biases") or []):
        lines.append(f"Vbias{i} {nets[b['port'].lower()]} 0 {float(b['volts']):.6g}")
    for i, c in enumerate(plan.get("controls") or []):
        lines.append(f"Vctl{i} {nets[c['port'].lower()]} 0 {float(c['volts']):.6g}")
    for i, ld in enumerate(plan.get("loads") or []):
        if "farads" in ld:
            lines.append(f"Cplan{i} {nets[ld['port'].lower()]} 0 {float(ld['farads']):.6g}")
        else:
            lines.append(f"Rplan{i} {nets[ld['port'].lower()]} 0 {float(ld['ohms']):.6g}")
    for i, pd in enumerate(plan.get("pads") or []):
        lines.append(f"Rpad{i} {nets[pd['port'].lower()]} pad{i} {PAD['ohms']:.6g}")
        lines.append(f"Cpad{i} pad{i} 0 {PAD['farads']:.6g}")
        lines.append(f"Rdrv{i} pad{i} 0 1e15")          # the drive test's load; open otherwise
    return sim.Testbench(sch=p, circuit="\n".join(lines), analyses=[".op"])


def run(plan, root, on_result=None):
    """Run a validated plan. Returns {findings, results: [{corner, temp, vscale, error, i_op, i_end, nodes}], bench,
    seconds}: the wall time is kept so a review can say where its time went."""
    t0 = time.time()
    r = _run(plan, root, on_result)
    if r.get("ok"):
        r["seconds"] = round(time.time() - t0, 1)
    return r


def _run(plan, root, on_result=None):
    errs = validate(plan, root)
    if errs:
        return dict(ok=False, errors=errs)
    tb = compile_bench(plan, root)
    tb.floating = undriven(plan, root)               # (their nodes never decide a finding: sim.startup_corner)
    # the planner's supplies are the bench's supplies, whatever their names
    names = {f"vplan{i}" for i in range(len(plan["supplies"]))}
    tb.supplies = lambda: [(f"Vplan{i}", p, float(v)) for i, (p, v) in enumerate(plan["supplies"].items())] \
        if names else []
    corners, temps, vscales = _pvt(plan)
    bench = "\n".join(l for l in tb.circuit.splitlines()
                      if l.startswith(("Vplan", "Vgnd", "Rplan", "Cplan", "Vbias", "Rtie", "Vctl", "Rpad", "Cpad", "Rdrv")))
    if plan["kind"] == "stability":
        nets = {n.lower(): n for n in _nets(tb.circuit)}
        circ, _, y = sim.break_net(tb.circuit, nets[plan["break"]["net"].lower()], plan["break"]["pins"])
        tb.circuit, tb.brk_y = circ, y
        sw = {}
        for c in corners:
            for (t, v), r in sim.loopgain_corner(tb, c, [(t, v) for t in temps for v in vscales], timeout=150).items():
                sw[(c, t, v)] = r
                if on_result:
                    on_result((c, t, v), *r)
        rows = [dict(corner=c, temp=t, vscale=v, error=e, **({} if not r else {k: r[k] for k in
                     ("dc_gain_db", "ugf", "pm", "gm_db", "pcf", "positive_dc", "f", "mag", "phase")}))
                for (c, t, v), (r, e) in sw.items()]
        return dict(ok=True, findings=checks.stability(sw), results=rows, bench=bench)
    if plan["kind"] == "drive":
        per = {}
        for c in corners:
            for k, r in sim.drive_corner(tb, c, temps, vscales, len(plan["pads"]), [None] + DRIVE_LOADS).items():
                per[(c,) + k] = r
                if on_result:
                    on_result((c,) + k, *r)
        rows = [dict(corner=c, temp=t, vscale=v, error=e, volts=r) for (c, t, v), (r, e) in per.items()]
        return dict(ok=True, findings=checks.drive(per, [p["port"] for p in plan["pads"]], BOARD_MIN,
                                                        floating=undriven(plan, root)), results=rows,
                    bench=bench)
    if plan["kind"] == "domains":
        sup = list(plan["supplies"].items())
        per = {}
        for v in vscales:
            on = {f"vplan{i}": val * v for i, (_, val) in enumerate(sup)}
            states = [(f"all rails on (supply x{v:g})", on)] + \
                [(f"{p} off, {', '.join(q for q, _ in sup if q != p)} on (supply x{v:g})", dict(on, **{f"vplan{i}": 0.0}))
                 for i, (p, _) in enumerate(sup)] * (len(sup) > 1)
            for c in corners:
                for (st, t), r in sim.op_states(tb, c, temps, states, timeout=300).items():
                    per[(st, c, t)] = r
                    if on_result:
                        on_result((st, c, t), *r)
        models = sim.device_models(tb.circuit + "\n" + sim.stdcells.defs_for(tb.circuit))
        rows = [dict(state=st, corner=c, temp=t, error=e) for (st, c, t), (r, e) in per.items()]
        return dict(ok=True, findings=checks.overstress(per, models), results=rows, bench=bench,
                    devices=len([m for m in models.values() if checks.rating(m)]))
    if plan["kind"] == "sequence":
        meta, scheds = {}, {}
        for name, sched, m in cases(plan):
            meta[name], scheds[name] = m, sched
        ref = next(iter(scheds))
        groups = [((name, c, v), c, v, sched) for name, sched in scheds.items() for c in corners for v in vscales]

        def suspect(key, coarse):
            base = coarse.get((ref, key[1], key[2])) or {}
            return any(_odd(r, (base.get(t) or (None,))[0] if key[0] != ref else None)
                       for t, (r, e) in coarse[key].items())

        got = _checked_sweep(tb, groups, temps, FAST, 300e-6, 300, suspect)
        per = {name: {} for name in scheds}
        for (name, c, v), res in got.items():
            for t, r in res.items():
                per[name][(c, t, v)] = r
                if on_result:
                    on_result((name, c, t, v), *r)
        per = {name: dict(sorted(sw.items(), key=lambda x: (corners.index(x[0][0]), vscales.index(x[0][2]))))
               for name, sw in per.items()}
        rows = [dict(case=name, corner=c, temp=t, vscale=v, error=e,
                     **({} if not r else dict(i_op=r["i_op"], i_end=r["i_end"], nodes=r["nodes"], state=checks.state(r))))
                for name, sw in per.items() for (c, t, v), (r, e) in sw.items()]
        fl = undriven(plan, root)
        found = held_inputs(plan, root, checks.sequence(per, meta, floating=fl), fl, FAST, 300e-6, 300, scheds[ref])
        return dict(ok=True, findings=found, results=rows, bench=bench, cases=list(per))
    got = _checked_sweep(tb, [((c, v), c, v, None) for c, v in worst_first(corners, vscales)], temps, 20e-6, 300e-6, 150,
                         lambda key, coarse: any(_odd(r) for r, e in coarse[key].values()))
    sw = {}
    for c in corners:
        for v in vscales:
            for t, r in got[(c, v)].items():
                sw[(c, t, v)] = r
                if on_result:
                    on_result((c, t, v), *r)
    rows = [dict(corner=c, temp=t, vscale=v, error=e,
                 **({} if not r else dict(i_op=r["i_op"], i_end=r["i_end"], nodes=r["nodes"],
                                          confirmed=r.get("confirmed"), swing=r.get("swing"))))
            for (c, t, v), (r, e) in sw.items()]
    fl = undriven(plan, root)
    return dict(ok=True, findings=held_inputs(plan, root, checks.startup(sw, floating=fl), fl, 20e-6, 300e-6, 150),
                results=rows, bench=bench)


def held_inputs(plan, root, findings, floating, ramp, settle, timeout, schedule=None):
    """An oscillation found while the test left inputs undriven, re-run at its worst condition with those inputs held
    by a source at each of HELD x the highest supply. A held input carries no signal back into the circuit, so a
    swing that remains comes from a loop of the circuit's own: the finding stays a warning and says at which level.
    When the circuit settles at every level, the swing needed a floating input (a gate left open couples the output
    back into itself): the finding becomes a note. Backtest v3 (2 Nov): 11 of the 15 oscillations on reviewed chips
    came from power-ups that named undriven inputs, most on logic gates and latches of chips that work. A level that
    does not finish leaves the warning as it was, and says what each level did. The re-runs have HELD_BUDGET seconds
    of their own when the review has a time budget: in backtest v3's 555 timer the first latch had spent its test's
    share, and its re-runs never started."""
    osc = [f for f in findings if f.get("rule") == "analog/oscillates" and f.get("severity") == "warn"]
    if not osc or not floating:
        return findings
    f = max(osc, key=lambda f: f.get("n_bad", 0))
    c, t, v = f["worst"]
    top = max(float(x) for x in plan["supplies"].values())
    levels = []
    with sim.until(HELD_BUDGET if sim.time_left() is not None else None):
        for frac in HELD:
            levels.append(_held_level(plan, root, floating, frac * top * v, (c, t, v), ramp, settle, timeout,
                                      schedule))
    f["held"] = levels
    names = ", ".join(sorted(floating))
    base = f["message"].split(" This test left ")[0]
    still = [x for x in levels if x["swing"]]
    if still:
        x = max(still, key=lambda x: x["swing"][1])
        f["message"] = (base + f" The test left {names} undriven; held at {x['volts']:g} V "
                        f"{'it still leaves' if len(floating) == 1 else 'they still leave'} {x['swing'][0]} swinging "
                        f"{x['swing'][1] * 1e3:.0f} mV, so the loop is unstable by itself.")
    elif all(x["state"] in ("settled", "dead") for x in levels):
        f["severity"] = "info"
        at = " / ".join(f"{x['volts']:g}" for x in levels)
        f["message"] = (base.replace(": a loop is unstable.", ".") + f" This test left {names} undriven, and held at "
                        f"{at} V the circuit settles every time: the swing needs a floating input (an open gate "
                        f"coupled to the output), not a loop of the circuit's own. Bias {names} as the chip does to "
                        f"be sure.")
    else:
        said = {"settled": "settles", "dead": "stays off", "unresolved": "is still moving at the end"}
        f["message"] += (f" Re-run with {names} held: " + "; ".join(
            f"at {x['volts']:g} V it {said.get(x['state'], 'did not finish (' + x['state'].split(':')[0] + ')')}"
            for x in levels) + ". Nothing is concluded from it.")
    return findings


def _held_level(plan, root, floating, volts, cond, ramp, settle, timeout, schedule):
    """One held-input re-run (see held_inputs): {volts, state, swing: (node, peak-to-peak) or None}."""
    c, t, v = cond
    volts = round(volts, 4)
    p2 = dict(plan, biases=list(plan.get("biases") or []) + [dict(port=q, volts=volts) for q in floating])
    tb = compile_bench(p2, root)
    tb.supplies = lambda: [(f"Vplan{i}", p, float(x)) for i, (p, x) in enumerate(plan["supplies"].items())]
    for hold in (settle, HELD_LONGER * settle):          # still moving at the end: held once more, longer
        r, e = sim.startup_checked(tb, c, [t], v, ramp=ramp, settle=hold, timeout=timeout, schedule=schedule).get(
            t, (None, "did not complete"))
        st = None if e or not r else checks.state(r)
        if st != "unresolved":
            break
    return dict(volts=volts, state=st or str(e)[:80],
                swing=(max(r["swing"].items(), key=lambda x: x[1]) if st == "oscillates" else None))


def undriven(plan, root):
    """The cell's pins this plan connects nothing to (no supply, ground, bias, control, tie, load or pad)."""
    rel = str(plan.get("cell", ""))
    if "#" in rel:
        ports = spice_cells.load(root, rel)[1] or []
    else:
        p = _cell(plan, root)
        ports = [m[1] for m in N.PORT_LABELS.findall(open(p, errors="replace").read())] if p else []
    used = set(plan.get("supplies") or {}) | set(plan.get("grounds") or [])
    used |= {t[k] for t in plan.get("ties") or [] for k in ("a", "b")}
    used |= {x.get("port") for k in ("biases", "controls", "loads", "pads") for x in plan.get(k) or []}
    used = {str(u).lower() for u in used if u}
    circ = _cell_circuit(plan, root) or ""
    reach = dc_groups(circ)
    driven = {reach(u) for u in used} | {reach(g) for g in ("0", "gnd")}
    return [q for q in ports if q.lower() not in used and reach(q) not in driven]


def dc_groups(circuit):
    """A function net -> its DC group in `circuit`: nets joined by anything that carries DC (a resistor, a source, a
    diode, a transistor's channel, recursively inside the design's subcircuits; a device the netlist does not define
    joins all its pins). A pin whose group holds no net the test drives floats, even when it has a DC path: the two
    terminals of a pass gate reach only each other (backtest row 12: an analog switch's IN and OUT, left undriven,
    drifted 70 mV and read as an oscillation)."""
    subs, top, cur = {}, [], None
    for line in re.sub(r"\n\s*\+", " ", circuit).splitlines():
        t = re.sub(r"'[^']*'|\{[^}]*\}", "", line).split()
        if not t or t[0].startswith("*"):
            continue
        if t[0].lower() == ".subckt":
            cur = t[1].lower()
            subs[cur] = ([x.lower() for x in t[2:] if "=" not in x], [])
            continue
        if t[0].lower().startswith(".ends"):
            cur = None
            continue
        if not t[0].startswith("."):
            (subs[cur][1] if cur else top).append([x.lower() for x in t if "=" not in x])
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def join(a, b):
        parent[find(a)] = find(b)

    def walk(lines, net, path, depth):
        for t in lines:
            k = t[0][0]
            if k == "c" or len(t) < 3:
                continue
            if k == "m" and len(t) >= 4:
                join(net(t[1]), net(t[3]))                      # drain - source: the channel (gate, body: no DC)
                continue
            if k == "x":
                pins, name = t[1:-1], t[-1]
                if MOS.match(name) and len(pins) >= 3:
                    join(net(pins[0]), net(pins[2]))
                elif RES.match(name) and len(pins) >= 2:
                    join(net(pins[0]), net(pins[1]))            # a poly resistor's third pin is its body: no DC
                elif name in subs and depth < 30:
                    inner, body = subs[name]
                    mp = dict(zip(inner, (net(p) for p in pins)))
                    pre = f"{path}{t[0]}/"
                    walk(body, lambda n, mp=mp, pre=pre: mp.get(n) or (n if n in ("0", "gnd") else pre + n), pre,
                         depth + 1)
                else:
                    for p in pins[1:]:                          # not defined here: assume it conducts
                        join(net(pins[0]), net(p))
                continue
            join(net(t[1]), net(t[2]))                          # R, L, D, V, I, E, ...
    walk(top, lambda n: n, "", 0)
    return lambda n: find(str(n).lower())


MOS = re.compile(r"(?i)^sky130_fd_pr__(n|p)fet\w*$|^gf180mcu_fd_pr__(n|p)fet\w*$")
RES = re.compile(r"(?i)^(sky130|gf180mcu)_fd_pr__res\w*$")


def dc_path(circuit, net):
    """True when `net` reaches anything but MOS gates and capacitors at the top level of `circuit`, following it into
    the design's own subcircuits: a pin with no DC path floats unless the test drives it. A device the netlist does not
    define (a standard cell, an unknown model) counts as a DC path, so a pin is called floating only when it surely is."""
    subs, top, cur = {}, [], None
    for line in re.sub(r"\n\s*\+", " ", circuit).splitlines():    # continuation lines joined (Magic's long pin lists)
        t = re.sub(r"'[^']*'|\{[^}]*\}", "", line).split()
        if not t or t[0].startswith("*"):
            continue
        if t[0].lower() == ".subckt":
            cur = t[1].lower()
            subs[cur] = ([x.lower() for x in t[2:] if "=" not in x], [])
            continue
        if t[0].lower().startswith(".ends"):
            cur = None
            continue
        if not t[0].startswith((".", "+")):
            (subs[cur][1] if cur else top).append([x for x in t if "=" not in x])

    def reaches(lines, n, seen):
        for t in lines:
            k = t[0][0].lower()
            if k == "c":
                continue
            if k == "m":
                if n in [x.lower() for x in (t[1:2] + t[3:4])]:
                    return True                       # drain or source (the gate and body carry no DC)
                continue
            if k == "x":
                pins, name = [x.lower() for x in t[1:-1]], t[-1].lower()
                if n not in pins:
                    continue
                if MOS.match(name):
                    if n in (pins[0:1] + pins[2:3]):
                        return True
                    continue
                if name not in subs or name in seen:
                    return True                       # not defined here (or recursive): assume it conducts
                inner = subs[name][0]
                for i, p in enumerate(pins):
                    if p == n and i < len(inner) and reaches(subs[name][1], inner[i], seen | {name}):
                        return True
                continue
            if n in [x.lower() for x in t[1:3]]:
                return True                           # R, L, D, V, I, E, ...: a DC path
        return False
    return reaches(top, net.lower(), frozenset())


def _odd(r, ref=None, vtol=0.1):
    """A default-step power-up that looks like a failure: dead, oscillating, resting away from its DC answer, or (in a
    sequence) ending elsewhere than the reference case at the same condition. Only an ordering hint: every verdict
    still comes from the fine-step check."""
    if not r:
        return False
    if checks.state(r) in ("dead", "oscillates"):
        return True
    if any(a is not None and b is not None and abs(a - b) > vtol for a, b in r["nodes"].values()):
        return True
    if ref:
        if checks.state(ref) != checks.state(r):
            return True
        return any(n in ref["nodes"] and b is not None and ref["nodes"][n][1] is not None and
                   abs(b - ref["nodes"][n][1]) > vtol for n, (a, b) in r["nodes"].items())
    return False


# the order power-up groups run in: the process corners where a start-up fails most often first (slow and fast, then the
# skewed ones, typical last), the low supply before nominal. Results do not depend on it; when a review's time budget
# runs out (sim.until), the conditions not reached are the least likely to fail rather than the last in a list.
CORNER_RANK = {"ss": 0, "ff": 1, "sf": 2, "fs": 3, "tt": 4}


def worst_first(corners, vscales):
    """[(corner, vscale)] with the extremes first: corners by CORNER_RANK, each supply scale furthest from 1 first,
    interleaved so the two worst corners both come before any second supply of either."""
    vs = sorted(vscales, key=lambda v: -abs(v - 1.0))
    cs = sorted(corners, key=lambda c: CORNER_RANK.get(c, 9))
    return [(c, v) for v in vs for c in cs[:2]] + [(c, v) for c in cs[2:] for v in vs]


def _checked_sweep(tb, groups, temps, ramp, settle, timeout, suspect):
    """Power-ups of every group (key, corner, vscale, schedule), each confirmed by sim.startup_checked. All default-step
    runs come first (sim.WORKERS at once); then the groups whose default result looks like a failure (suspect(key, coarse))
    take their fine-step checks, on their own budget (sim.SUSPECT_BUDGET), before any other group starts its own; the rest
    share sim.FINE_BUDGET. The fine-step checks also run sim.WORKERS at once: a budget counts simulator seconds (each
    run subtracts its own), so it buys the same simulation as one at a time, in less wall time. Returns
    {key: {temp: (result, err)}}."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=sim.WORKERS) as ex:     # each run is its own ngspice process
        futs = {key: sim.spawn(ex, sim.startup_corner, tb, c, temps, v, ramp, settle, timeout, sched)
                for key, c, v, sched in groups}
        coarse = {key: f.result() for key, f in futs.items()}
    sus, rest = sim.budget(sim.SUSPECT_BUDGET), sim.budget()
    flag = {key: suspect(key, coarse) for key, *_ in groups}
    out = {}
    for phase, fine in ((True, sus), (False, rest)):            # every suspect is checked before any other group
        with ThreadPoolExecutor(max_workers=sim.WORKERS) as ex:
            futs = {key: sim.spawn(ex, sim.startup_checked, tb, c, temps, v, ramp=ramp, settle=settle, timeout=timeout,
                                   schedule=sched, fine=fine, coarse=coarse[key])
                    for key, c, v, sched in groups if flag[key] == phase}
            out.update({key: f.result() for key, f in futs.items()})
    return {key: out[key] for key, *_ in groups}


def bench_deck(plan, root, corner, temp, vscale=1.0, case=None):
    """The testbench a validated plan simulates, as one ngspice deck at one condition: the designer's cell from the
    repository, the plan's supplies, pad loads and stimuli. A power-up or sequence test runs what the engine ran there,
    the DC answer and then the power-up from 0 V (for a sequence, of the named case); the other kinds run the operating
    point. The PDK line names the standard sky130 library (not this server's trimmed copy), so the deck runs on any
    machine with the open PDK."""
    errs = validate(plan, root)
    if errs:
        return None, "; ".join(errs)
    tb = compile_bench(plan, root)
    tb.supplies = lambda: [(f"Vplan{i}", p, float(v)) for i, (p, v) in enumerate(plan["supplies"].items())]
    if plan.get("kind") == "sequence":
        cs = {n: s for n, s, _ in cases(plan)}
        sched = cs.get(case) if case else next(iter(cs.values()))
        if sched is None:
            return None, f"no case {case!r} in this sequence test"
        text = sim.powerup_deck(tb, corner, int(temp), float(vscale), ramp=FAST, schedule=sched)
    elif plan.get("kind") == "powerup":
        text = sim.powerup_deck(tb, corner, int(temp), float(vscale))
    else:
        text = sim.deck(tb, corner, int(temp), float(vscale))
    return portable(text, root), None


def portable(text, root):
    """A deck as a designer runs it: the PDK line names the standard sky130 library (not this server's trimmed copy)
    and no path of this server's workspace remains."""
    text = re.sub(r'^\.lib "[^"]*" (\w+)$', lambda m: "* point this at your sky130A install (volare / ciel)\n"
                  f'.lib "sky130A/libs.tech/ngspice/sky130.lib.spice" {m.group(1)}', text, count=1, flags=re.M)
    return text.replace(os.path.realpath(root) + os.sep, "").replace(root.rstrip(os.sep) + os.sep, "")


def wave(plan, root, corner, temp, vscale=1.0, case=None):
    """The power-up waveform of a validated power-up or sequence plan at one condition (sim.powerup_wave); for a
    sequence plan, of the named case (default: the reference)."""
    errs = validate(plan, root)
    if errs:
        return None, "; ".join(errs)
    tb = compile_bench(plan, root)
    tb.supplies = lambda: [(f"Vplan{i}", p, float(v)) for i, (p, v) in enumerate(plan["supplies"].items())]
    if plan.get("kind") == "sequence":
        cs = {n: s for n, s, _ in cases(plan)}
        sched = cs.get(case) if case else next(iter(cs.values()))
        if sched is None:
            return None, f"no case {case!r} in this sequence test"
        return sim.powerup_wave(tb, corner, int(temp), float(vscale), ramp=FAST, schedule=sched)
    return sim.powerup_wave(tb, corner, int(temp), float(vscale))

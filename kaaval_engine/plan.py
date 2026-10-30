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
import os, re

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
    """Run a validated plan. Returns {findings, results: [{corner, temp, vscale, error, i_op, i_end, nodes}], bench}."""
    errs = validate(plan, root)
    if errs:
        return dict(ok=False, errors=errs)
    tb = compile_bench(plan, root)
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
        return dict(ok=True, findings=checks.drive(per, [p["port"] for p in plan["pads"]], BOARD_MIN), results=rows,
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
        per = {}
        meta = {}
        fine = sim.budget()
        for name, sched, m in cases(plan):
            meta[name] = m
            sw = {}
            for c in corners:
                for v in vscales:
                    for t, r in sim.startup_checked(tb, c, temps, v, ramp=FAST, settle=300e-6, timeout=300,
                                                   schedule=sched, fine=fine).items():
                        sw[(c, t, v)] = r
                        if on_result:
                            on_result((name, c, t, v), *r)
            per[name] = sw
        rows = [dict(case=name, corner=c, temp=t, vscale=v, error=e,
                     **({} if not r else dict(i_op=r["i_op"], i_end=r["i_end"], nodes=r["nodes"], state=checks.state(r))))
                for name, sw in per.items() for (c, t, v), (r, e) in sw.items()]
        return dict(ok=True, findings=checks.sequence(per, meta), results=rows, bench=bench, cases=list(per))
    sw = {}
    fine = sim.budget()
    for c in corners:
        for v in vscales:
            for t, r in sim.startup_checked(tb, c, temps, v, ramp=20e-6, settle=300e-6, timeout=150,
                                            fine=fine).items():
                sw[(c, t, v)] = r
                if on_result:
                    on_result((c, t, v), *r)
    rows = [dict(corner=c, temp=t, vscale=v, error=e,
                 **({} if not r else dict(i_op=r["i_op"], i_end=r["i_end"], nodes=r["nodes"],
                                          confirmed=r.get("confirmed"), swing=r.get("swing"))))
            for (c, t, v), (r, e) in sw.items()]
    return dict(ok=True, findings=checks.startup(sw), results=rows, bench=bench)


def bench_deck(plan, root, corner, temp, vscale=1.0):
    """The testbench a validated plan simulates, as one ngspice deck at one condition with an operating-point analysis:
    the designer's cell from the repository, the plan's supplies, pad loads and stimuli. The PDK line names the
    standard sky130 library (not this server's trimmed copy), so the deck runs on any machine with the open PDK."""
    errs = validate(plan, root)
    if errs:
        return None, "; ".join(errs)
    tb = compile_bench(plan, root)
    tb.supplies = lambda: [(f"Vplan{i}", p, float(v)) for i, (p, v) in enumerate(plan["supplies"].items())]
    text = sim.deck(tb, corner, int(temp), float(vscale))
    text = re.sub(r'^\.lib "[^"]*" (\w+)$', lambda m: "* point this at your sky130A install (volare / ciel)\n"
                  f'.lib "sky130A/libs.tech/ngspice/sky130.lib.spice" {m.group(1)}', text, count=1, flags=re.M)
    return text.replace(os.path.realpath(root) + os.sep, "").replace(root.rstrip(os.sep) + os.sep, ""), None


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

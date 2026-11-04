"""startup.py — a start-up circuit for a block that can wake up dead: Muse Spark designs it, Kaaval's engine proves it.

For a power-up finding (analog/no_startup, two_states, marginal_startup) from a planned test, Muse Spark reads the
finding, the cell's netlist and its ports, and designs the missing start-up circuit: a few sky130 transistors (and
resistors, if it needs them) on the cell's own nets and new internal ones (STARTUP_SCHEMA). Kaaval writes the cell
again with those devices added (a SPICE subcircuit of its own, beside the design; nothing in the repository changes),
and runs the same power-up test at all 45 conditions. It is verified only when the circuit starts at every one of them
and settles where its DC analysis says, with its working current within BIAS_TOL of the original design's. A failed
round goes back to Muse Spark with what was measured (ROUNDS at most).
"""
import re

from app import engine, planner

ROUNDS = 3
BIAS_TOL = 0.15
ALL = dict(corners=["tt", "ss", "ff", "sf", "fs"], temps=[-40, 27, 125], vscales=[0.9, 1.0, 1.1])
RULES = ("analog/no_startup", "analog/two_states", "analog/marginal_startup")
MODELS = {"nfet": "sky130_fd_pr__nfet_01v8", "pfet": "sky130_fd_pr__pfet_01v8"}
NET = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")

STARTUP_SCHEMA = {"name": "kaaval_startup", "schema": {
    "type": "object", "additionalProperties": False, "required": ["devices", "why"],
    "properties": {
        "devices": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "type", "d", "g", "s", "b", "W", "L", "value"],
            "properties": {"name": {"type": "string"}, "type": {"type": "string", "enum": ["nfet", "pfet", "res"]},
                           "d": {"type": "string"}, "g": {"type": "string"}, "s": {"type": "string"},
                           "b": {"type": "string"}, "W": {"type": "number"}, "L": {"type": "number"},
                           "value": {"type": "string"}}}},
        "why": {"type": "string"}}}}

STARTUP_SYSTEM = """You are a senior analog designer. A sky130 block (1.8 V devices sky130_fd_pr nfet_01v8 / pfet_01v8)
can power up dead: from 0 V it can stay in its zero-current state, although its DC analysis finds a working bias.
Design the start-up circuit it is missing, the way a careful designer would: it must kick the block out of the
zero-current state at every process / temperature / supply condition, then switch itself off (or draw negligible
current) once the block is biased, so the working point does not move. Answer with devices:
- type nfet or pfet: d, g, s, b are nets; W and L in micrometres (W 0.42..50, L 0.15..20); value "".
- type res: d and s are its two nets (g and b ""), value like "200k"; W and L 0.
Use the block's own nets by their exact names and new internal nets (letters, digits, _); never rename a port. Bodies:
nfet to the ground net, pfet to the supply net. At most 5 devices. Names must not clash with the block's (use MS1,
MS2, RS1...). Every design is simulated at all 45 conditions; you will be told what was measured if it fails. Explain
in "why", in three or four sentences a designer can check, how it starts the block and why it then turns off."""


def _ports(cell_rec):
    return [p if isinstance(p, str) else p.get("name") or p.get("port") for p in cell_rec.get("ports") or []]


def lines(devices, nets, ports):
    """SPICE lines for the proposed devices, and the reasons any are refused."""
    out, errors, names = [], [], set()
    for d in devices:
        n = re.sub(r"[^A-Za-z0-9_]", "", str(d.get("name") or ""))
        t = d.get("type")
        if not n or n.upper() in names or n.upper() in nets["devices"]:
            errors.append(f"{d.get('name')}: the name is empty or already used")
            continue
        names.add(n.upper())
        pins = [d.get("d"), d.get("g"), d.get("s"), d.get("b")] if t in MODELS else [d.get("d"), d.get("s")]
        if not all(isinstance(p, str) and NET.match(p) for p in pins):
            errors.append(f"{n}: every pin needs a net name ({pins})")
            continue
        if t in MODELS:
            w, l = float(d.get("W") or 0), float(d.get("L") or 0)
            if not (0.42 <= w <= 50 and 0.15 <= l <= 20):
                errors.append(f"{n}: W={w} L={l} is outside W 0.42..50, L 0.15..20")
                continue
            out.append(f"X{n if n.upper().startswith('M') else 'M' + n} {' '.join(pins)} {MODELS[t]} W={w:g} L={l:g} nf=1")
        elif t == "res":
            v = str(d.get("value") or "").strip().lower()
            if not re.match(r"^\d+(\.\d+)?(meg|[kmu])?$", v):
                errors.append(f"{n}: resistor value {d.get('value')!r} is not a number like 200k")
                continue
            out.append(f"R{n if n.upper().startswith('R') else 'R' + n} {pins[0]} {pins[1]} {v}")
        else:
            errors.append(f"{n}: type {t!r} is not nfet, pfet or res")
    return out, errors


def cell_text(cell_rec, name, extra):
    """The cell as a SPICE subcircuit named `name`, with the extra device lines."""
    return (f"* {cell_rec['cell']} with a start-up circuit designed by Muse Spark (Kaaval, for verification)\n"
            f".subckt {name} {' '.join(_ports(cell_rec))}\n{cell_rec['netlist'].strip()}\n"
            + "".join(l + "\n" for l in extra) + f".ends {name}\n")


def _bias(rows):
    """{condition: DC operating current} of a power-up test's result rows."""
    return {(r.get("case"), r.get("corner"), r.get("temp"), r.get("vscale")): abs(r.get("i_op") or 0)
            for r in rows if not r.get("error") and r.get("i_op")}


def fix(files, ws, finding, original, log=lambda *a, **k: None, arm="muse"):
    """The design loop for one power-up finding. `original`: the planned test's stored results (plan, results).
    Returns {verified, by, kind: "startup", devices, spice, why, rounds, n_conditions, started, bias_shift}."""
    if not planner.configured(arm):
        raise planner.PlannerError("Muse Spark is not connected: start Kaaval with its key set.")
    plan = dict(original["plan"])
    cells = {c["cell"]: c for c in engine.cells(ws)}
    rec = cells.get(plan["cell"])
    if not rec or not rec.get("netlist"):
        raise ValueError(f"the cell {plan['cell']} has no netlist to add a start-up circuit to")
    ports = _ports(rec)
    devs = {l.split()[0].upper().lstrip("X") for l in rec["netlist"].splitlines() if l.strip() and l[0] not in "*+."}
    devs |= {l.split()[0].upper() for l in rec["netlist"].splitlines() if l.strip() and l[0] not in "*+."}
    base = _bias(original.get("results") or [])
    name = re.sub(r"\W", "_", plan["cell"].split("/")[-1].split("#")[-1].replace(".sch", "").replace(".spice", "")) + "_startup"
    path = f"kaaval_fix/{name}.spice"
    msgs = [{"role": "system", "content": STARTUP_SYSTEM},
            {"role": "user", "content": (
                f"# The finding\n{finding.get('title') or finding.get('message', '')}\n\n"
                f"# The block {plan['cell']}: ports {', '.join(ports)}\n{rec['netlist'][:8000]}\n\n"
                f"# The power-up test that found it\nsupplies {plan.get('supplies')}, grounds {plan.get('grounds')}, "
                f"loads {plan.get('loads')}\nDC operating current at the conditions it ran: "
                + ", ".join(f"{k[1]} {k[2]} °C ×{k[3]}: {v * 1e6:.2f} uA" for k, v in list(base.items())[:12]))}]
    rounds = []
    for i in range(ROUNDS):
        out, _ = planner._chat(arm, msgs, schema=STARTUP_SCHEMA)
        proposed, why = out.get("devices") or [], str(out.get("why", "")).strip()
        extra, errors = lines(proposed, {"devices": devs}, ports)
        log(f"Muse Spark designs a start-up circuit (round {i + 1}): {len(extra)} device(s): "
            + "; ".join(extra) + (f". {why}" if why else ""))
        res = {}
        if errors or not extra:
            res = dict(ok=False, why="; ".join(errors) or "no device proposed")
        else:
            text = cell_text(rec, name, extra)
            ws2 = engine.upload(dict(files, **{path: text}))
            r = engine.plan(ws2, dict(plan, cell=f"{path}#{name}", **ALL))
            if not r.get("ok"):
                res = dict(ok=False, why="the engine refused the circuit: " + "; ".join(r.get("errors") or [])[:400])
            else:
                rows = [x for x in r.get("results") or [] if not x.get("error")]
                bad = [f for f in r.get("findings") or [] if f["rule"] in RULES]
                new = _bias(rows)
                shift = max((abs(new[k] - base[k]) / base[k] for k in new if k in base and base[k] > 0), default=None)
                started = len(rows) - sum(f.get("n_bad", 0) for f in bad if f["rule"] == "analog/no_startup")
                res = dict(ok=not bad and len(rows) >= 40 and (shift is None or shift <= BIAS_TOL), n=len(rows),
                           started=started, bad=[f["message"][:220] for f in bad][:3], shift=shift,
                           other=[f["message"][:160] for f in r.get("findings") or [] if f["rule"] not in RULES][:3])
                if res["ok"]:
                    log(f"Verified: with Muse Spark's start-up circuit, {plan['cell']} starts at all {len(rows)} "
                        f"conditions" + (f", working current within {shift * 100:.1f} % of the original" if shift is not None else ""),
                        "info")
                    rounds.append(dict(devices=extra, why=why, result=res))
                    return dict(verified=True, by="muse", kind="startup", devices=extra, spice=text, why=why,
                                rounds=rounds, n_conditions=len(rows), bias_shift=shift, cell=plan["cell"])
        rounds.append(dict(devices=extra, why=why, result=res))
        said = res.get("why") or (
            f"it still powers up dead or wrong: {' | '.join(res['bad'])}" if res.get("bad") else
            f"it starts, but the working current moves {res['shift'] * 100:.0f} % from the original (limit "
            f"{BIAS_TOL * 100:.0f} %)" if res.get("shift") is not None and res["shift"] > BIAS_TOL else
            f"only {res.get('n')} of 45 conditions simulated")
        log(f"Round {i + 1} not verified: {said}", "warn")
        msgs += [{"role": "assistant", "content": str(out)},
                 {"role": "user", "content": f"Simulated at all 45 conditions: {said}. Design it again."}]
    return dict(verified=False, by="muse", kind="startup", rounds=rounds, n_conditions=45, cell=plan["cell"],
                why=f"no design passed all 45 conditions in {ROUNDS} rounds")

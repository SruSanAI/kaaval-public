"""planner.py — Muse Spark plans the review a senior analog designer would run, the engine proves it.

The designer's own testbenches only test what the designer thought of. Muse Spark reads the whole design (docs, every
circuit cell with its ports and netlist, and what happened when the designer's testbenches ran) and decides which
blocks can fail in silicon and how: a reference with no start-up path, a loop that may not settle, an output that a
load drags down. It answers in a fixed JSON schema: what each block is, with the evidence for it, and test plans.

Plans are data. Minnal's engine checks every plan against the circuit (the cell exists, every port is one of its
nets, every value is physical), builds the deck itself and runs it at the planned PVT conditions; a refused plan goes
back to the model once with the engine's reasons. Nothing the model writes is ever executed as simulator input.

Arms (for the ablation, same code path):
  muse   Muse Spark (Meta Model API, Responses API). MUSE_API_KEY (or MODEL_API_KEY), MUSE_MODEL, MUSE_BASE_URL
  small  any smaller OpenAI-compatible model.          SMALL_API_KEY, SMALL_MODEL, SMALL_BASE_URL
  rules  no model, brute force: power-up every cell at all 45 conditions, supplies and grounds guessed from pin names
  floor  no model: only the designer's own testbenches (the plain review)
Keys live only in this server's environment and never reach the browser.
"""
import json, os, re, time, urllib.error, urllib.request

from app import engine

ARMS = {
    "muse": ("MUSE_BASE_URL", "https://api.meta.ai/v1", "MUSE_MODEL", "muse-spark-1.3", "MUSE_API_KEY"),
    "small": ("SMALL_BASE_URL", "", "SMALL_MODEL", "", "SMALL_API_KEY"),
}
CORNERS = ["tt", "ss", "ff", "sf", "fs"]
MAX_PLANS = 4

SYSTEM = """You are a senior analog IC design reviewer. A designer has published an open-silicon chip design (SkyWater
sky130, xschem schematics). Their own testbenches only cover what they thought of. Find the blocks that could fail in
silicon and plan tests that would show it.

You receive the project's docs, every circuit cell (its ports and its netlist) and the outcome of running the
designer's own testbenches.
1. For each cell that matters, say what it is, quoting the netlist evidence.
2. Name its silicon risks, from your own analog design judgement.
3. Plan tests the engine can run. Available test kinds:
   powerup    the cell is powered from 0 V by the supplies you name and held at each PVT condition you choose; the
              engine reports whether it settles at the operating point its DC analysis gives, and if not, how.
   stability  the loop gain of a feedback loop is measured at a cut you choose (a net, and the element pins that go
              on one side of the cut); the engine reports unity-gain frequency, phase margin and gain margin at each
              condition. Element names are as they appear in the cell's netlist; pins are d, g, s, b for transistors
              or 1, 2, ... in netlist order. A tie (a resistor you place between two ports) is element Rtie<index>,
              pin 1 on its first port; ties let you close a loop, e.g. an amplifier's output to its inverting input.
   sequence   the cell is powered up the way a chip powers it: each rail first in turn (the others 10 µs, 100 µs or 1 ms later),
              fast (2 µs) and slow (1 ms) ramps, and the enables / resets you list as controls rising with the rails
              or released after them. The engine reports any sequence in which the cell comes up dead, oscillating or
              in another state than with every rail together. Use it for cells with more than one supply domain, an
              enable or reset, or a start-up circuit; at most 128 power-ups (cases x conditions), so name few
              conditions, e.g. corners tt ss ff at 27 °C.
   domains    for a cell with supplies at different voltages (1.8 V and 3.3 V): every transistor's voltages are solved
              with all rails on and with each rail off while the others are up, and judged against the device's
              rating (1.8 V thin-oxide devices against 3.3 V nodes: a missing level shifter or thick-oxide device).
   drive      for a cell output that leaves the chip (listed in pads): the load on its pad is swept (open, 10 Mohm, 1 Mohm,
              100 kohm, 10 kohm) and the engine reports its output resistance and whether 1 Mohm already moves it.
   A plan names the cell, its supply ports and voltages, its ground ports, DC biases on input ports, controls
   (enable / reset ports and their active voltage; sequence only), loads on ports (ohms or farads), pads (ports that
   leave the chip through a Tiny Tapeout analog pad: the engine adds the pad path, 500 ohm and 5 pF; the drive test
   sweeps the board's load), ties, the cut (stability only), and the process corners (tt ss ff sf fs), temperatures (°C)
   and supply scales to run (at most 45 conditions).
For every block also label each port's role (supply, ground, enable, reset, analog_out, analog_in, bias, digital),
quoting the evidence (a doc line, a label, the devices on it).
Use port names exactly as listed. Do not invent cells or ports. Plan only tests whose purpose you can state."""

SCHEMA = {
    "name": "review_plan",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False, "required": ["blocks", "plans"],
        "properties": {
            "blocks": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["cell", "function", "evidence", "risks", "startup_path", "ports"],
                "properties": {
                    "cell": {"type": "string"}, "function": {"type": "string"}, "evidence": {"type": "string"},
                    "ports": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["port", "role", "evidence"],
                        "properties": {"port": {"type": "string"}, "evidence": {"type": "string"},
                                       "role": {"type": "string", "enum": ["supply", "ground", "enable", "reset",
                                                                           "analog_out", "analog_in", "bias",
                                                                           "digital"]}}}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "startup_path": {"type": "string", "enum": ["yes", "no", "unclear", "not_applicable"]}}}},
            "plans": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["cell", "kind", "supplies", "grounds", "biases", "controls", "loads", "pads", "ties",
                             "cut", "corners", "temps", "vscales", "why"],
                "properties": {
                    "cell": {"type": "string"},
                    "kind": {"type": "string", "enum": ["powerup", "stability", "sequence", "domains", "drive"]},
                    "controls": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["port", "volts"],
                        "properties": {"port": {"type": "string"}, "volts": {"type": "number"}}}},
                    "pads": {"type": "array", "items": {"type": "string"}},
                    "biases": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["port", "volts"],
                        "properties": {"port": {"type": "string"}, "volts": {"type": "number"}}}},
                    "ties": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["a", "b", "ohms"],
                        "properties": {"a": {"type": "string"}, "b": {"type": "string"}, "ohms": {"type": "number"}}}},
                    "cut": {"type": "object", "additionalProperties": False, "required": ["net", "pins"],
                            "properties": {"net": {"type": "string"},
                                           "pins": {"type": "array", "items": {"type": "string"}}}},
                    "supplies": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["port", "volts"],
                        "properties": {"port": {"type": "string"}, "volts": {"type": "number"}}}},
                    "grounds": {"type": "array", "items": {"type": "string"}},
                    "loads": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["port", "unit", "value"],
                        "properties": {"port": {"type": "string"}, "unit": {"type": "string", "enum": ["ohms", "farads"]},
                                       "value": {"type": "number"}}}},
                    "corners": {"type": "array", "items": {"type": "string", "enum": CORNERS}},
                    "temps": {"type": "array", "items": {"type": "number"}},
                    "vscales": {"type": "array", "items": {"type": "number"}},
                    "why": {"type": "string"}}}}}}}


class PlannerError(RuntimeError):
    pass


# Meta's own reference client reads MODEL_API_KEY / MODEL_API_BASE_URL / MODEL_API_MODEL; ours MUSE_*. Either works.
ALIASES = {"MUSE_API_KEY": "MODEL_API_KEY", "MUSE_BASE_URL": "MODEL_API_BASE_URL", "MUSE_MODEL": "MODEL_API_MODEL"}


def _env(name):
    return os.environ.get(name) or os.environ.get(ALIASES.get(name, ""), "")


def configured(arm):
    a = ARMS.get(arm)
    return bool(a and _env(a[4]) and (_env(a[0]) or a[1]) and (_env(a[2]) or a[3]))


def _call(arm, body, timeout):
    base_env, base_def, _, _, key_env = ARMS[arm]
    req = urllib.request.Request((_env(base_env) or base_def).rstrip("/") + "/responses",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {_env(key_env)}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _output_text(j):
    """The model's text from a Responses API reply (what the SDK calls output_text)."""
    if isinstance(j.get("output_text"), str):
        return j["output_text"]
    return "".join(c.get("text", "") for item in j.get("output") or [] if item.get("type") == "message"
                   for c in item.get("content") or [] if c.get("type") in ("output_text", "text"))


def _chat(arm, messages, timeout=180):
    """One planning call on the Responses API (the format Meta's own reference client uses: OpenAI-compatible,
    POST /v1/responses). The answer must follow SCHEMA: a strict json_schema format is asked first; if the
    endpoint does not take it, JSON mode with the schema in the instructions (the engine validates every plan
    either way). Returns (parsed JSON, usage)."""
    base_env, base_def, model_env, model_def, key_env = ARMS[arm]
    if not configured(arm):
        raise PlannerError(f"The {arm} planner is not connected: set {key_env} on the Kaaval server.")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [{"role": m["role"], "content": [{"type": "output_text" if m["role"] == "assistant" else "input_text",
                                              "text": m["content"]}]} for m in messages if m["role"] != "system"]
    body = {"model": _env(model_env) or model_def, "instructions": system, "input": turns,
            "text": {"format": {"type": "json_schema", "name": SCHEMA["name"], "schema": SCHEMA["schema"],
                                "strict": True}}}
    t = time.time()
    try:
        try:
            j = _call(arm, body, timeout)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            body["text"] = {"format": {"type": "json_object"}}
            body["instructions"] = system + "\n\nAnswer with one JSON object that follows this JSON schema exactly:\n" + \
                json.dumps(SCHEMA["schema"])
            j = _call(arm, body, timeout)
    except urllib.error.HTTPError as e:
        raise PlannerError(f"{arm} model {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise PlannerError(f"{arm} model unreachable ({e.reason})") from None
    except (TimeoutError, OSError) as e:
        raise PlannerError(f"{arm} model did not answer in time ({type(e).__name__})") from None
    try:
        out = json.loads(_output_text(j))
    except ValueError:
        raise PlannerError(f"{arm} model answered without valid JSON") from None
    usage = j.get("usage") or {}
    return out, dict(seconds=round(time.time() - t, 1), format=body["text"]["format"]["type"],
                     prompt_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
                     completion_tokens=usage.get("output_tokens", usage.get("completion_tokens")))


def context(docs, cells, floor):
    """The design as the reviewer reads it: docs, then each cell (ports, size, netlist), then the floor's outcome."""
    parts = ["# Project docs\n" + (docs or "(none)")[:20000], "# Circuit cells"]
    for c in cells:
        parts.append(f"## {c['cell']}\nports: {', '.join(c['ports'])}\ndevices: {c['devices']}\n```spice\n"
                     f"{c['netlist']}\n```")
    parts.append("# The designer's own testbenches, as run by the engine\n" + (floor or "(none ran)"))
    return "\n\n".join(parts)


def _to_engine(p):
    e = dict(cell=p["cell"], kind=p["kind"], supplies={s["port"]: s["volts"] for s in p["supplies"]},
             grounds=p["grounds"], biases=p.get("biases") or [], ties=p.get("ties") or [],
             loads=[{"port": l["port"], l["unit"]: l["value"]} for l in p.get("loads") or []],
             pads=[{"port": x} for x in p.get("pads") or []],
             corners=p["corners"] or None, temps=p["temps"] or None, vscales=p["vscales"] or None, why=p["why"])
    if p["kind"] == "stability":
        e["break"] = p.get("cut") or {}
    if p["kind"] == "sequence":
        e["controls"] = p.get("controls") or []
    return e


def review(arm, ws, docs, floor, log=lambda kind, text, **kw: None):
    """Plan and run the review for one arm. Returns {arm, blocks, plans: [{plan, result}], usage}."""
    if arm == "floor":
        return dict(arm=arm, blocks=[], plans=[], usage=[])
    if arm == "rules":
        return _rules(ws, log, max_cells=int(os.environ.get("KAAVAL_BASELINE_CELLS", "6")), docs=docs)
    cells = engine.cells(ws)
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": context(docs, cells, floor)}]
    log("plan", f"{arm} is reading {len(cells)} circuit cells and the docs")
    out, use = _chat(arm, msgs)
    usage = [use]
    for b in out["blocks"]:
        log("block", f"{b['cell']}: {b['function']} — {b['evidence']}", risks=b["risks"], startup=b["startup_path"])
    done = []
    for p in out["plans"][:MAX_PLANS]:
        ep = _to_engine(p)
        log("plan", f"Test planned on {p['cell']}: {p['why']}", plan=ep)
        r = engine.plan(ws, ep)
        if not r.get("ok") and r.get("errors"):
            # one correction round: the engine's reasons go back to the model
            log("plan", "The engine refused the plan: " + "; ".join(r["errors"]))
            fix_msgs = msgs + [{"role": "assistant", "content": json.dumps(out)},
                               {"role": "user", "content": "The engine refused this plan:\n" + json.dumps(p) +
                                "\nReasons:\n- " + "\n- ".join(r["errors"]) +
                                "\nReturn the same JSON with that plan corrected (other plans unchanged)."}]
            out2, use2 = _chat(arm, fix_msgs)
            usage.append(use2)
            cand = [q for q in out2["plans"] if q["cell"] == p["cell"]]
            if cand:
                ep = _to_engine(cand[0])
                r = engine.plan(ws, ep)
        done.append(dict(plan=ep, result=r))
        for f in r.get("findings") or []:
            log("finding", f["message"], rule=f["rule"], cell=ep["cell"])
    return dict(arm=arm, blocks=out["blocks"], plans=done, usage=usage)


SUP = re.compile(r"(?i)^(v?dd\w*|v[ad]?pwr|vcc\w*|avdd\w*|dvdd\w*|vdd3v3|vpwr\w*)$")
GND = re.compile(r"(?i)^(v?ss\w*|v?gnd\w*|agnd|dgnd)$")
OUT = re.compile(r"(?i)^(v?out\w*|\w*_out|vref\w*|\w*ref|v?bgr\w*|iout\w*|ua\[?\d\]?)$")
CTL = re.compile(r"(?i)^(ena?|enable\w*|en_\w+|\w*_en|rst\w*|reset\w*|pd|pwr_?dn|pdn)$")


STDCELL = re.compile(r"(?i)\bsky130_fd_sc_\w+")


def digital_only(netlist):
    """A cell built only from standard cells (flip-flops, gates, buffers) and no transistors of its own: a digital block.
    Its power-up state is set by its reset, and a flip-flop has two states by design, so an analog power-up test says
    nothing about it (and on a whole SAR controller costs most of a review). Any transistor, or any instance that is
    not a standard cell (a sub-circuit of the project's own), keeps the cell analog."""
    inst = [l for l in (netlist or "").splitlines() if re.match(r"(?i)^\s*x", l)]
    return bool(inst) and all(STDCELL.search(l) and "sky130_fd_pr__" not in l for l in inst)


THICK = re.compile(r"(?i)g5v0d10v5|g5v0d16v0|_05v0|sky130_fd_sc_hvl")
# 1.8 V-only parts: thin-oxide transistors and the 1.8 V standard-cell libraries (hd, hdll, hs, ms, ls, lp)
THIN = re.compile(r"(?i)sky130_fd_pr__[np]fet_01v8(_lvt|_hvt)?\b|sky130_fd_sc_(hd|hdll|hs|ms|ls|lp)__")


def rail_volts(port, netlist):
    """A guess at a supply port's voltage without a model: 3.3 V when its name says so (VAPWR, 3v3); else 1.8 V when
    any 1.8 V-only part (thin-oxide transistor, hd / hs / ms / ls standard cell) has its source, bulk or power pin on
    it; else 3.3 V when a thick-oxide (5 V-rated) device or a 3.3 V (hvl) standard cell does; 1.8 V otherwise.
    Returns (volts, evidence)."""
    p = port.lower()
    thick = thin = None
    for line in (netlist or "").splitlines():
        w = line.split()
        if len(w) < 3 or w[0][0] not in "xXmM":
            continue
        nets = [x.lower() for x in w[1:] if "=" not in x]
        on = p in (nets[2:4] if "fet" in line.lower() else nets[:-1])     # a transistor's source / bulk, a cell's pins
        if on and thick is None and len(w) > 5 and THICK.search(line):
            thick = w[0]
        if on and thin is None and THIN.search(line):
            thin = w[0]
    # a 1.8 V-only part on the rail wins: thick-oxide parts work at 1.8 V, thin ones do not survive 3.3 V (30 Oct
    # backtest: a flash ADC with a thick-oxide buffer and an sky130_fd_sc_hd encoder on one VDD was run at 3.3 V)
    if re.search(r"(?i)vapwr|3v3", port):            # Tiny Tapeout's 3.3 V pin is 3.3 V whatever sits on it (a
        return 3.3, f"the name {port}"                  # 1.8 V part there is then an overstress finding)
    if thin:
        return 1.8, (f"{thin} is a 1.8 V part on {port}" + (f" ({thick} is thick-oxide; it also works at 1.8 V)"
                                                             if thick else ""))
    if thick:
        return 3.3, f"{thick} is a thick-oxide / 3.3 V device on {port}"
    return 1.8, f"no 3.3 V device on {port}"


# the PDK's own standard-cell and I/O libraries (sky130_fd_sc_hd__dfxtp_1, sky130_fd_io__..., the efabless and OSU
# cells): an LVS or extracted netlist expands them into transistors, but they are not the designer's circuit
FOUNDRY_CELL = re.compile(r"(?i)^(sky130_(fd|ef|osu)_(sc|io)\w*|gf180mcu_fd_(sc|io)\w*)__")


def used_inside(cells, name):
    """{cell name: a cell that instantiates it} over the design's own cells: a block used inside another block is
    internal, and its outputs never reach a pad (an instance line ends with the subcircuit's name)."""
    names = {name(c) for c in cells}
    out = {}
    for c in cells:
        for line in (c.get("netlist") or "").splitlines():
            t = line.split()
            if len(t) > 2 and t[0][:1].lower() == "x" and t[-1].lower() in names and t[-1].lower() != name(c):
                out.setdefault(t[-1].lower(), c["cell"])
    return out


def _rules(ws, log, max_cells=20, docs=""):
    """The no-model baseline: every cell whose pins name a supply and a ground is powered up at all 45 conditions.
    3.3 V for pins named like the analog 3.3 V rail, 1.8 V otherwise. Cells with two supply voltages or pins named
    like an enable / reset also get a sequence test (rail order and speed); cells with supplies at two voltages also
    get the cross-domain overstress test."""
    done = []
    # one test per circuit: the same cell often exists as a schematic plus xschem-written and layout-extracted
    # netlists; prefer the schematic, then a plain netlist, then an extracted one (parasitic copies last)
    def name(c):
        n = c["cell"].split("#")[-1] if "#" in c["cell"] else os.path.splitext(os.path.basename(c["cell"]))[0]
        return re.sub(r"(?i)_parax$|\.mag$", "", n).lower()
    rank = lambda c: (0 if "#" not in c["cell"] else 2 if re.search(r"(?i)\.(sim|lvs|pex|rc)\.|parax|_rc\b|pex", c["cell"]) else 1)
    best = {}
    cells = engine.cells(ws)
    for c in sorted(cells, key=lambda c: (rank(c), -c.get("devices", 0))):
        best.setdefault(name(c), c)
    inner = used_inside(cells, name)
    for c in sorted(best.values(), key=lambda c: -c.get("devices", 0))[:max_cells]:
        sup = [p for p in c["ports"] if SUP.match(p)]
        gnd = [p for p in c["ports"] if GND.match(p)]
        if not sup or not gnd:
            continue
        if FOUNDRY_CELL.match(name(c)):
            log("plan", f"rules: {c['cell']} not powered up: a foundry standard cell ({name(c)}), characterised by "
                        f"the PDK, not the design's own circuit")
            continue
        if digital_only(c.get("netlist")):
            log("plan", f"rules: {c['cell']} not powered up: standard cells only, a digital block (its reset sets its "
                        f"power-up state)")
            continue
        volts = {p: rail_volts(p, c.get("netlist")) for p in sup}
        if "the chip has no 3.3 V supply" in (docs or ""):        # runner.chip_supplies: the top level has no VAPWR
            volts = {p: (1.8, "the chip's top level has no VAPWR: only the 1.8 V supply") for p in sup}
        guess = "; ".join(f"{p} {v:g} V ({why})" for p, (v, why) in volts.items())
        ep = dict(cell=c["cell"], kind="powerup", supplies={p: v for p, (v, _) in volts.items()}, grounds=gnd,
                  loads=[], corners=CORNERS, temps=[-40, 27, 125], vscales=[0.9, 1.0],
                  why="every cell, every condition; rail voltages guessed: " + guess)
        plans = [ep]
        # chip context, by name only: a cell with two supply pins, or pins named like an enable or reset, is also
        # powered up in every rail order and speed (controls driven to the 1.8 V rail, active high)
        ctl = [p for p in c["ports"] if CTL.match(p)]
        if len(ep["supplies"]) > 1 or ctl:
            plans.append(dict(cell=c["cell"], kind="sequence", supplies=ep["supplies"], grounds=gnd, loads=[],
                              controls=[{"port": p, "volts": 1.8} for p in ctl[:2]],
                              corners=["tt", "ss", "ff"], temps=[27], vscales=[1.0],
                              why="every rail order, by pin names"))
        if len(set(ep["supplies"].values())) > 1:
            plans.append(dict(cell=c["cell"], kind="domains", supplies=ep["supplies"], grounds=gnd, loads=[],
                              corners=["tt", "ss", "ff"], temps=[-40, 27, 125], vscales=[1.0, 1.1],
                              why="1.8 V devices next to a 3.3 V rail; rail voltages guessed: " + guess))
        outs = [p for p in c["ports"] if OUT.match(p) and p not in sup + gnd]
        if outs and name(c) in inner:
            log("plan", f"rules: {c['cell']} no pad drive test: it is used inside {inner[name(c)]}, so its outputs "
                        f"do not reach a pad")
        elif outs:
            plans.append(dict(cell=c["cell"], kind="drive", supplies=ep["supplies"], grounds=gnd, loads=[],
                              pads=[{"port": p} for p in outs[:2]], corners=CORNERS, temps=[-40, 27, 125],
                              vscales=[1.0], why="outputs by pin names, each on a Tiny Tapeout pad; rail voltages "
                                                 "guessed: " + guess))
        for ep in plans:
            log("plan", f"rules: {ep['kind']} {c['cell']}", plan=ep)
            try:
                r = engine.plan(ws, ep)
            except engine.EngineError as e:               # one slow or broken cell never ends the review
                r = dict(ok=False, errors=[str(e)])
            done.append(dict(plan=ep, result=r))
    return dict(arm="rules", blocks=[], plans=done, usage=[])

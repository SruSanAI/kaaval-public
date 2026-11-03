"""loops.py — the feedback loops a designer already closed in a testbench, and their loop gain across PVT.

A testbench that puts an op-amp in feedback (a follower, an inverting stage, a regulator's divider) holds the loop
the chip will run. This module finds it from the netlist alone, no names guessed: an instance whose symbol marks a pin
as an output (dir=out), whose output net reaches one of the same instance's inputs directly or through R, L, C or
0 V elements, without passing a net a source holds (a supply, a reference, a stimulus, ground: an AC ground ends the
path) or an inductor of 1 H or more (a DC-only feedback path of an open-loop AC bench). The
loop is cut at that output pin and its loop gain measured by Tian's method (sim.break_net, sim.loopgain_corner) at
every corner, temperature and supply; checks.stability judges the margins, at the conditions where the loop is a
linear amplifier loop (linear()). The testbench's own AC sources are set to zero for this, so only the probe drives
the loop.
"""
import os, re

from kaaval_engine import netlist as N
from kaaval_engine.xsch import _props, parse

GROUND = re.compile(r"(?i)^(0|gnd|vss|vgnd|agnd|dgnd)$")


def directions(sch_path):
    """{instance name (lower case): [pin direction per netlist node]} for the schematic's subcircuit instances, from
    their symbols (bus pins expanded, as the netlister writes them)."""
    local = os.path.dirname(os.path.abspath(sch_path))
    out = {}
    for kind, f, props in parse(open(sch_path, errors="replace").read()):
        if kind != "C":
            continue
        path = N._find_sym(f[0], local)
        if not path:
            continue
        sd = N.symbol(path)
        if sd["type"] != "subcircuit":
            continue
        name = _props(props).get("name")
        if name:
            out[name.lower()] = [sd["dirs"].get(n, "") for n, _, _ in sd["pins"] for _ in N.expand(n)]
    return out


def _top(circuit):
    """[(name, nodes, value text)] of the top-level element lines."""
    out, depth = [], 0
    for line in re.sub(r"\n\s*\+", " ", circuit).splitlines():
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
        elif low.startswith(".ends"):
            depth -= 1
        elif depth == 0 and low and low[0] not in "*.":
            t = line.split()
            k = t[0][0].lower()
            if k == "x":
                nodes = [x for x in t[1:-1] if "=" not in x]
                out.append((t[0], nodes, t[-1]))
            elif len(t) >= 3:
                out.append((t[0], t[1:3], " ".join(t[3:])))
    return out


def _dc(text):
    """The value of a plain DC source ("0.9", "dc 0"), None for anything else (an AC or time-varying stimulus)."""
    m = re.fullmatch(r"(?i)\s*(?:dc\s+)?([-+\d.eE]+)\s*", text or "")
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


def _value(text):
    m = re.match(r"(?i)\s*([-+\d.eE]+)([a-z]*)", text or "")
    if not m:
        return None
    try:
        return float(m.group(1)) * {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9,
                                    "p": 1e-12, "f": 1e-15}.get(next((k for k in ("meg", "t", "g", "k", "m", "u", "n",
                                                                                  "p", "f") if m.group(2).lower()
                                                                     .startswith(k)), ""), 1.0)
    except ValueError:
        return None


def find(circuit, dirs):
    """Loops closed around one instance: [{inst, net, pin, via}] where `net` is the instance's output net, `pin` the
    break pin ("x1.2": the instance's node 2, its output) and `via` the input it returns to and how."""
    els = _top(circuit)
    held = set()                                       # nets a source holds: an AC ground ends a feedback path
    for name, nodes, val in els:
        k = name[0].lower()
        if (k == "v" and _dc(val) != 0.0) or k in "ef":
            held.update(n.lower() for n in nodes if not GROUND.match(n))
    held |= {n.lower() for _, nodes, _ in els for n in nodes if GROUND.match(n)}
    edges = {}
    for name, nodes, val in els:
        k = name[0].lower()
        # an inductor of 1 H or more is the designer's AC-open DC feedback (an open-loop AC bench): no loop there
        if k == "l" and (_value(val) or 0) >= 1.0:
            continue
        if k in "rlc" or (k == "v" and _dc(val) == 0.0):
            a, b = (n.lower() for n in nodes[:2])
            edges.setdefault(a, []).append((b, name))
            edges.setdefault(b, []).append((a, name))
    found = []
    for name, nodes, _ in els:
        d = dirs.get(name.lower())
        if name[0].lower() != "x" or not d or len(d) != len(nodes):
            continue
        # a symbol that marks no pin as an output (every pin inout) offers each pin as one: Tian's loop gain is the
        # same whichever side of the cut is which, so a loop is found once whichever of its pins is the driver
        outs = {"out"} if "out" in d else {"out", "inout", ""}
        ins = {}
        for i, n in enumerate(nodes):
            if d[i] in ("in", "inout", ""):
                ins.setdefault(n.lower(), []).append(i)
        done = set()
        for i, n in enumerate(nodes):
            if d[i] not in outs or n.lower() in held or n.lower() in done:
                continue
            seen, todo, path = {n.lower()}, [n.lower()], {n.lower(): []}
            hit = None
            while todo and not hit:
                cur = todo.pop(0)
                if any(j != i for j in ins.get(cur, [])):
                    hit = cur
                    break
                for nxt, el in edges.get(cur, []):
                    if nxt not in seen and nxt not in held:
                        seen.add(nxt)
                        path[nxt] = path[cur] + [el]
                        todo.append(nxt)
            if hit:
                j = next(j for j in ins[hit] if j != i)
                done.update({n.lower(), hit})
                found.append(dict(inst=name, net=n, pin=f"{name}.{i + 1}",
                                  via=f"back to its pin {j + 1} ({nodes[j]})" +
                                      (f" through {', '.join(path[hit])}" if path[hit] else " directly")))
    return found


def no_ac(circuit):
    """The circuit with every top-level source's AC magnitude removed: only the loop probe drives the AC analysis."""
    out, depth = [], 0
    for line in circuit.splitlines():
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
        elif low.startswith(".ends"):
            depth -= 1
        elif depth == 0 and low[:1] in ("v", "i"):
            line = re.sub(r"(?i)\s+ac\s+[-+\d.eE]+(\s+[-+\d.eE]+(?=\s|$))?", "", line)
        out.append(line)
    return "\n".join(out)


def connected(circuit, inst):
    """The circuit with only the top-level elements joined to instance `inst` through shared nets (ground excepted):
    a testbench often holds spare copies on nets of their own, whose floating nodes keep the operating point from
    solving. Subcircuit definitions and every dot line are kept."""
    els = _top(circuit)
    nets = {e[0].lower(): {n.lower() for n in e[1] if not GROUND.match(n)} for e in els}
    keep, todo = {inst.lower()}, [inst.lower()]
    while todo:
        cur = todo.pop()
        for name, ns in nets.items():
            if name not in keep and ns & nets[cur]:
                keep.add(name)
                todo.append(name)
    out, depth = [], 0
    for line in re.sub(r"\n\s*\+", " ", circuit).splitlines():
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
        elif low.startswith(".ends"):
            depth -= 1
        elif depth == 0 and low and low[0] not in "*." and line.split()[0].lower() not in keep:
            continue
        out.append(line)
    return "\n".join(out)


LINEAR_DB = (0.0, 140.0)    # DC loop gain of an amplifier in negative feedback; beyond it, a regenerative circuit


def linear(r):
    """Why a loop-gain result is not a linear amplifier loop at that condition, or None when it is one: negative
    feedback with a DC loop gain between LINEAR_DB. Below 0 dB there is no loop gain to speak of (the stage is off or
    switched away); far above any amplifier's gain, the operating point is the metastable point of a latch, a Schmitt
    trigger or a relaxation oscillator (the 555 timer of backtest row 11: -170 dB at most conditions, +193 dB at one);
    positive feedback at DC is a latch or an oscillator by design. Margins mean something only for the first."""
    g = r.get("dc_gain_db")
    if r.get("positive_dc"):
        return "positive feedback at DC (a latch or an oscillator by design)"
    if g is None or g <= LINEAR_DB[0]:
        return f"no loop gain at DC ({g:.0f} dB): the loop is open or switched off here" if g is not None else "no DC gain"
    if g >= LINEAR_DB[1]:
        return f"DC loop gain {g:.0f} dB: a regenerative circuit at its metastable point, not an amplifier"
    return None


def sweep(tb, loop, corners=None, conds=None, timeout=300):
    """Loop gain of one found loop at every condition: {(corner, temp, vscale): (margins, err)} for checks.stability.
    `tb` is the designer's Testbench (sim.Testbench.from_sch); it is not changed."""
    import copy
    from kaaval_engine import checks, sim
    corners = corners or checks.CORNERS
    conds = conds or [(t, v) for t in checks.TEMPS for v in checks.VSCALES]
    t2 = copy.copy(tb)
    try:
        circ, _, y = sim.break_net(no_ac(connected(tb.circuit, loop["inst"])), loop["net"], [loop["pin"]])
    except ValueError as e:
        return {(c, t, v): (None, str(e)) for c in corners for t, v in conds}
    t2.circuit, t2.brk_y = circ, y
    t2.analyses = [".op"]
    out = {}
    for c in corners:
        for (t, v), (r, e) in sim.loopgain_corner(t2, c, conds, timeout=timeout).items():
            why = None if e or not r else linear(r)
            out[(c, t, v)] = (None, "not judged: " + why) if why else (r, e)
    return out


def deck(tb, loop, corner="tt", temp=27, vscale=1.0):
    """The loop-gain measurement of one found loop at one condition, as a plain ngspice deck a designer can run: the
    testbench as drawn (only the elements joined to the loop's instance, its own AC sources set to zero), the loop
    cut at the instance's output, both of Tian's injections, and the loop gain, unity-gain frequency and phase
    margin computed by ngspice itself (printed, and T(f) written to loopgain.txt)."""
    import copy
    from kaaval_engine import sim
    t2 = copy.copy(tb)
    circ, _, y = sim.break_net(no_ac(connected(tb.circuit, loop["inst"])), loop["net"], [loop["pin"]])
    t2.circuit, t2.analyses = circ, [".op"]
    ctl = "\n".join([
        f"* {loop['inst']} in feedback, its output {loop['net']} {loop['via']}: cut there (kv_brk_x | {y})",
        "alter @vkvz[acmag]=1", "alter @ikvz[acmag]=0", "ac dec 20 1 10g",
        "alter @vkvz[acmag]=0", "alter @ikvz[acmag]=1", "ac dec 20 1 10g",
        "* Tian's method: T = (Y12 + Y21) / (Y11 + Y22) of the two-port seen at the cut",
        f"let vxa = ac1.v(kv_brk_x)", f"let vya = ac1.v({y})", "let iza = ac1.i(vkvz)",
        "let vb = ac2.v(kv_brk_x)", "let izb = ac2.i(vkvz)",
        "let s1 = (1 - izb) / vb", "let s2 = izb / vb",
        "let y11 = (-iza - s1 * vya) / (vxa - vya)", "let y21 = (iza - s2 * vya) / (vxa - vya)",
        "let t = ((s1 - y11) + y21) / (y11 + (s2 - y21))",
        "let tdb = db(t)", "let tph = 180 / pi * cph(t)",
        "meas ac ugf when tdb=0 fall=1", "meas ac phase_at_ugf find tph at=ugf",
        "let pm = 180 + phase_at_ugf", "print tdb[0] pm", "wrdata loopgain.txt tdb tph"])
    return sim.deck(t2, corner, int(temp), float(vscale), control=ctl)

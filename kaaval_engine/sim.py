"""sim.py — run a repo's testbench under OUR control across process, voltage and temperature.

The circuit comes from kaaval_engine.netlist (text only). From the designer's command blocks we take only analysis
statements, read as text (.op/.dc/.tran/.ac and their .control forms op/dc/tran/ac), never .include/.lib, shell,
source or write. We add the PDK library at a chosen corner, the temperature and a supply scale, and our own .control
that reports every transistor's operating point (BSIM4 `show`), so the same deck runs at every PVT condition.

    from kaaval_engine import sim
    tb = sim.Testbench.from_sch("xschem/tb_x.sch")
    ops = sim.op_points(tb, corner="ss", temp=-40, vscale=0.9)
"""
import os, re, shutil, subprocess, tempfile
from dataclasses import dataclass, field

from kaaval_engine import netlist as N
from kaaval_engine import pdk, stdcells
from kaaval_engine.xsch import _block, _props, parse

from kaaval_engine.paths import PDK_LIB
TRIM = os.environ.get("KAAVAL_PDK_TRIM", "1") == "1"   # per-design trimmed library (kaaval_engine.pdk); identical results
SUPPLY = re.compile(r"^(v?dd[a-z0-9_]*|vdpwr|vapwr|vpwr|vcc|avdd|vdda|vdd_hi|vdd3v3|vdd1v8)$", re.I)
ANALYSIS = re.compile(r"^\s*\.?(op|dc|tran|ac)\b(.*)$", re.I)
SAFE_DOT = re.compile(r"^\s*\.(param|ic|nodeset|temp|tran|dc|ac|op)\b", re.I)
# simulator options a designer's results depend on; anything else (scale, files, shell) is never taken
SAFE_OPT = {"wnflag", "gmin", "reltol", "abstol", "vntol", "chgtol", "method", "itl1", "itl2", "itl4", "maxord",
            "temp", "tnom", "savecurrents"}


@dataclass
class Testbench:
    sch: str
    circuit: str                          # netlist lines from the schematic (no commands)
    analyses: list = field(default_factory=list)   # designer's analysis statements, as dot-lines
    params: list = field(default_factory=list)     # designer's .param / .ic / .nodeset lines
    options: dict = field(default_factory=dict)    # designer's simulator options from SAFE_OPT

    @classmethod
    def from_sch(cls, sch):
        text = open(sch, errors="replace").read()
        analyses, params, options = [], [], {}
        for kind, f, props in parse(text):
            if kind != "C" or not any(k in f[0] for k in ("code", "simulator_commands")):
                continue
            pr = _props(props)
            if str(pr.get("spice_ignore", "")).strip().lower() in ("true", "1"):
                continue                      # a command block the designer switched off
            val = pr.get("value", "")
            for line in val.replace("\\n", "\n").splitlines():
                s = line.strip()
                if not s or s.startswith("*"):
                    continue
                if re.match(r"^\s*\.?options?\b", s, re.I):
                    for k, v in re.findall(r"(\w+)\s*=\s*(\S+)", s):
                        if k.lower() in SAFE_OPT:
                            options[k.lower()] = v
                    continue
                if SAFE_DOT.match(s):
                    (params if re.match(r"^\s*\.(param|ic|nodeset)", s, re.I) else analyses).append(s)
                else:
                    m = ANALYSIS.match(s)
                    if m and not s.startswith("."):
                        analyses.append("." + m.group(1).lower() + m.group(2))
        return cls(sch=sch, circuit=N.netlist(sch), analyses=analyses, params=params, options=options)

    def supplies(self):
        """(name, +node, value) of independent DC voltage sources driving a supply-named net."""
        out = []
        for line in self.circuit.splitlines():
            p = line.split()
            if len(p) >= 4 and p[0][0].lower() == "v":
                val = p[3] if p[3].lower() != "dc" else (p[4] if len(p) > 4 else "")
                try:
                    v = float(val)
                except ValueError:
                    continue
                if SUPPLY.match(p[1]) or SUPPLY.match(p[2]):
                    out.append((p[0], p[1], v))
        return out


def _scaled(circuit, supplies, vscale):
    if vscale == 1.0:
        return circuit
    names = {s[0].lower(): s[2] for s in supplies}
    out = []
    for line in circuit.splitlines():
        p = line.split()
        if p and p[0].lower() in names:
            i = 3 if p[3].lower() != "dc" else 4
            p[i] = f"{names[p[0].lower()] * vscale:.6g}"
            line = " ".join(p)
        out.append(line)
    return "\n".join(out)


SHOW = "show m : id vgs vds vth vdsat gm gds"


def deck(tb, corner="tt", temp=27, vscale=1.0, control=None):
    """A complete, inert ngspice deck: PDK at `corner`, temperature, supplies scaled, our own control block."""
    body = _scaled(tb.circuit, tb.supplies(), vscale)
    cells = stdcells.defs_for(tb.circuit)          # standard cells the design instantiates, from the PDK
    if cells:
        body += "\n" + cells
    ctl = control or f"op\n{SHOW}"
    # sky130 bins wide multi-finger devices on W/nf; the usual xschem setting unless the designer chose otherwise
    opts = dict({"wnflag": "1"}, **tb.options)
    opt = " ".join(f"{k}={v}" for k, v in opts.items() if k not in ("temp", "savecurrents"))
    lib = pdk.lib_for(tb.circuit + "\n" + cells, corner) if TRIM else PDK_LIB
    return (f"* Kaaval run: {os.path.basename(tb.sch)} corner={corner} temp={temp} vscale={vscale}\n"
            f'.lib "{lib}" {corner}\n.temp {temp}\n.option warn=0 {opt}\n' + "\n".join(tb.params) + "\n" + body +
            f"\n.control\n{ctl}\n.endc\n.end\n")


def run(deck_text, timeout=120):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "deck.sp")
        open(p, "w").write(deck_text)
        try:
            r = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=timeout, cwd=d)
            return r.stdout + r.stderr, None
        except subprocess.TimeoutExpired:
            return "", "timeout"


def parse_show(out):
    """{device: {param: value, 'model': ...}} from ngspice `show` blocks."""
    devs, cols = {}, []
    for line in out.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "device":
            cols = p[1:]
            for c in cols:
                devs.setdefault(c, {})
            continue
        if cols and len(p) == len(cols) + 1:
            for c, v in zip(cols, p[1:]):
                try:
                    devs[c][p[0]] = float(v)
                except ValueError:
                    devs[c][p[0]] = v
    return devs


def region(d):
    """Operating region of a MOSFET from its op point (signs handled for pmos)."""
    vgs, vds, vth, vdsat = (abs(d.get(k, 0.0)) if isinstance(d.get(k), float) else 0.0
                            for k in ("vgs", "vds", "vth", "vdsat"))
    if vgs < vth - 0.05:
        return "subth" if abs(d.get("id", 0)) > 1e-12 else "off"
    return "sat" if vds >= vdsat else "triode"


def short(name):
    """m.x1.xm2.msky130_fd_pr__nfet_01v8 -> x1.xm2 (the designer's hierarchy)."""
    parts = name.split(".")
    return ".".join(parts[1:-1]) if len(parts) > 2 else name


def op_points(tb, corner="tt", temp=27, vscale=1.0):
    out, err = run(deck(tb, corner, temp, vscale))
    if err:
        return None, err
    if "error" in out.lower() and "show" not in out:
        return None, next((l for l in out.splitlines() if "rror" in l), "error")
    d = parse_show(out)
    return {short(k): dict(v, region=region(v)) for k, v in d.items()}, None


def op_points_corner(tb, corner, conds, timeout=600):
    """{(temp, vscale): (ops, err)} for one process corner in ONE ngspice session.

    Loading the sky130 library is most of a run's time, so it is loaded once per corner; temperature and supply are
    then stepped inside the session (`option temp`, `alter` on each supply source) with an operating point at each.
    """
    sup = tb.supplies()
    lines = []
    for i, (t, v) in enumerate(conds):
        lines.append(f"option temp={t}")
        for name, _, val in sup:
            lines.append(f"alter {name.lower()} dc={val * v:.6g}")
        lines.append(f"op\necho KAAVAL_COND {i}\n{SHOW}")
    out, err = run(deck(tb, corner, 27, 1.0, control="\n".join(lines)), timeout=timeout)
    res = {}
    if err:
        return {c: (None, err) for c in conds}
    chunks = re.split(r"^KAAVAL_COND (\d+)\s*$", out, flags=re.M)
    got = {int(chunks[i]): chunks[i + 1] for i in range(1, len(chunks) - 1, 2)}
    for i, c in enumerate(conds):
        if i not in got:
            res[c] = (None, "no operating point (did not converge)")
            continue
        d = parse_show(got[i])
        res[c] = ({short(k): dict(v, region=region(v)) for k, v in d.items()}, None) if d else (None, "no devices")
    return res


def device_models(circuit):
    """{device path as op_points names it ("x1.xmn"): model name}, resolved through the subcircuit hierarchy of a
    flat netlist (ngspice's `show` truncates model names, so they are read from the text)."""
    subs, top, cur = {}, [], None
    for line in circuit.splitlines():
        p = line.split()
        if not p or p[0][0] in "*+":
            continue
        low = p[0].lower()
        if low == ".subckt":
            cur = subs.setdefault(p[1].lower(), [])
        elif low == ".ends":
            cur = None
        elif low[0] == "x":
            name = next((w for w in reversed(p[1:]) if "=" not in w), "")
            (top if cur is None else cur).append((low, name.lower()))
    out = {}

    def walk(elems, prefix, depth):
        for el, name in elems:
            path = f"{prefix}.{el}" if prefix else el
            if name in subs and depth < 30:
                walk(subs[name], path, depth + 1)
            elif name.startswith("sky130_fd_pr__"):
                out[path] = name
    walk(top, "", 0)
    return out


def op_states(tb, corner, temps, states, timeout=600):
    """{(state name, temp): (ops, err)} in ONE ngspice session: every MOSFET's operating point with the sources set
    as each state says. A state is (name, {source name lower: volts}); sources it does not name keep their value
    (e.g. ("vdpwr off", {"vplan1": 0.0}): the chip with one rail not yet up)."""
    base = {name.lower(): val for name, _, val in tb.supplies()}
    lines, keys = [], []
    for sname, set_ in states:
        for t in temps:
            lines.append(f"option temp={t}")
            for src, val in dict(base, **set_).items():
                lines.append(f"alter {src} dc={val:.6g}")
            lines.append(f"op\necho KAAVAL_COND {len(keys)}\n{SHOW}")
            keys.append((sname, t))
    out, err = run(deck(tb, corner, 27, 1.0, control="\n".join(lines)), timeout=timeout)
    if err:
        return {k: (None, err) for k in keys}
    chunks = re.split(r"^KAAVAL_COND (\d+)\s*$", out, flags=re.M)
    got = {int(chunks[i]): chunks[i + 1] for i in range(1, len(chunks) - 1, 2)}
    res = {}
    for i, k in enumerate(keys):
        d = parse_show(got[i]) if i in got else None
        res[k] = ({short(n): v for n, v in d.items()}, None) if d else (None, "no operating point (did not converge)")
    return res


def drive_corner(tb, corner, temps, vscales, npads, loads, timeout=600):
    """{(temp, vscale): ({pad index: [volts at each load]}, err)} for one corner in ONE ngspice session: the DC voltage
    at every pad with element Rdrv<i> set to each load in turn (None = open)."""
    sup = tb.supplies()
    lines, keys = [], []
    for t in temps:
        for v in vscales:
            lines.append(f"option temp={t}")
            for name, _, val in sup:
                lines.append(f"alter {name.lower()} dc={val * v:.6g}")
            for j, r in enumerate(loads):
                lines += [f"alter rdrv{i} r={r or 1e15:.6g}" for i in range(npads)]
                lines.append("op")
                lines += [f"let kdrv{i} = v(pad{i})" for i in range(npads)]
                lines.append(f"echo KAAVAL_DRV {len(keys)} {j} " + " ".join(f"$&kdrv{i}" for i in range(npads)))
            keys.append((t, v))
    out, err = run(deck(tb, corner, 27, 1.0, control="\n".join(lines)), timeout=timeout)
    if err:
        return {k: (None, err) for k in keys}
    got = {}
    for m in re.finditer(r"^KAAVAL_DRV (\d+) (\d+) (.*)$", out, re.M):
        got.setdefault(int(m.group(1)), {})[int(m.group(2))] = [float(x) for x in m.group(3).split()]
    res = {}
    for n, k in enumerate(keys):
        g = got.get(n, {})
        res[k] = (({i: [g[j][i] for j in range(len(loads))] for i in range(npads)}, None) if len(g) == len(loads)
                  else (None, "no operating point at every load (did not converge)"))
    return res


# ---------------------------------------------------------------- switching circuits: the designer's own transient
SI = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9}


def _num(s):
    m = re.match(r"^([+-]?[0-9.]+(?:e[+-]?\d+)?)(meg|[fpnumkg])?", s.strip().lower())
    return float(m.group(1)) * SI.get(m.group(2) or "", 1.0) if m else None


def tran_window(tb, cap=50e-6):
    """(tstep, tstop) from the designer's .tran, the stop time capped so a sweep stays fast."""
    for a in tb.analyses:
        p = a.split()
        if p and p[0].lower() == ".tran" and len(p) >= 3:
            step, stop = _num(p[1]), _num(p[2])
            if step and stop:
                stop = min(stop, cap)
                return max(step, stop / 20000), stop
    return None


def output_nets(tb):
    """Named top-level nets that are neither supplies nor driven directly by a source: the circuit's outputs."""
    top, driven, nets = [], set(), set()
    depth = 0
    for line in tb.circuit.splitlines():
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
        elif low.startswith(".ends"):
            depth -= 1
        elif depth == 0 and line.strip() and not line.startswith(("*", ".")):
            top.append(re.sub(r"'[^']*'|\{[^}]*\}|\"[^\"]*\"", "", line).split())
    for p in top:
        t = p[0][0].lower()
        if t in "vi" and len(p) >= 3:
            driven.update(x.lower() for x in p[1:3])
        if t in "vircld" and len(p) >= 3:
            pins = p[1:3]
        elif t == "m" and len(p) >= 5:
            pins = p[1:5]
        elif t == "x":
            args = [w for w in p[1:] if "=" not in w]
            pins = args[:-1]                      # the last bare word is the subcircuit name
        else:
            pins = []
        nets.update(x for x in pins if not re.fullmatch(r"\d+|net\d+|gnd|0", x.lower()))
    return sorted(n for n in nets if n.lower() not in driven and not SUPPLY.match(n) and
                  not re.match(r"(?i)^(v?ss|vgnd|gnd|agnd|dgnd)$", n))


def tran_corner(tb, corner, conds, nets, window, timeout=900):
    """{(temp, vscale): ({net: {mean, pp, freq}}, err)}: the transient at each condition of one corner in ONE session,
    each output measured over the last quarter of the run (after start-up)."""
    step, stop = window
    # ngspice cannot name vectors with brackets (ua[0]); rename every bus-style net consistently in our own deck
    safe = lambda n: re.sub(r"\[(\w+)\]", r"_\1_", n)
    tb = Testbench(sch=tb.sch, circuit=re.sub(r"(\S+)\[(\w+)\]", lambda m: f"{m.group(1)}_{m.group(2)}_", tb.circuit),
                   analyses=tb.analyses, params=tb.params, options=tb.options)
    orig = {safe(n): n for n in nets}
    nets = [safe(n) for n in nets]
    sup = tb.supplies()
    tmp = tempfile.mkdtemp()
    # a designer's .save lines would keep only their own vectors; we need every output node
    lines = ["save all"]
    for i, (t, v) in enumerate(conds):
        lines.append(f"option temp={t}")
        for name, _, val in sup:
            lines.append(f"alter {name.lower()} dc={val * v:.6g}")
        lines.append(f"tran {step:.4g} {stop:.4g}")
        lines.append(f"wrdata {tmp}/c{i}.txt " + " ".join(f"v({n})" for n in nets))
        lines.append(f"echo KAAVAL_TRAN {i}")
    out, err = run(deck(tb, corner, 27, 1.0, control="\n".join(lines)), timeout=timeout)
    res = {}
    for i, c in enumerate(conds):
        p = os.path.join(tmp, f"c{i}.txt")
        if err or not os.path.exists(p):
            res[c] = (None, err or "did not complete")
            continue
        cols = [[] for _ in range(len(nets) + 1)]
        for line in open(p):
            xs = line.split()
            if len(xs) >= 2 * len(nets):
                try:
                    vals = [float(x) for x in xs]
                except ValueError:
                    continue
                cols[0].append(vals[0])
                for k in range(len(nets)):
                    cols[k + 1].append(vals[2 * k + 1])
        t = cols[0]
        if len(t) < 10:
            res[c] = (None, "no waveform")
            continue
        start = next(j for j, x in enumerate(t) if x >= 0.75 * t[-1])
        meas = {}
        for k, n in enumerate(nets):
            y = cols[k + 1][start:]
            tt = t[start:]
            mean = sum(y) / len(y)
            pp = max(y) - min(y)
            ups = [tt[j] for j in range(1, len(y)) if y[j - 1] < mean <= y[j]] if pp > 1e-3 else []
            freq = (len(ups) - 1) / (ups[-1] - ups[0]) if len(ups) >= 3 and ups[-1] > ups[0] else 0.0
            meas[orig.get(n, n)] = dict(mean=mean, pp=pp, freq=freq)
        res[c] = (meas, None)
    shutil.rmtree(tmp, ignore_errors=True)
    return res


# ---------------------------------------------------------------- start-up: power the circuit up from 0 V
WAVE = re.compile(r"(?i)\b(pulse|sin|pwl|exp|sffm|am|trrandom)\b\s*\(?\s*([-+0-9.eE]+[a-z]*)?")


def _dc_value(rest):
    """The DC (operating-point) value of an independent source from the words after its nodes: an explicit `DC x`, a
    bare value, or else the waveform's initial value (what ngspice uses for the operating point)."""
    words = rest.replace("(", " ( ").replace(")", " ) ").split()
    for i, w in enumerate(words):
        if w.lower() == "dc" and i + 1 < len(words):
            return _num(words[i + 1])
    if words and _num(words[0]) is not None and not words[0].lower().startswith(("ac",)):
        return _num(words[0])
    m = WAVE.search(rest)
    if m and m.group(2):
        return _num(m.group(2))
    return 0.0 if m or re.match(r"(?i)^\s*ac\b", rest) else None


EDGE = 1e-9                        # rise / fall time of a digitally driven control


def _ramped(circuit, ramp, vscale, supplies, schedule=None):
    """Every top-level independent source becomes `DC x PWL(0 0 ramp x)` with x its operating-point value: the
    operating point is unchanged, while a transient starts from an unpowered circuit (all sources 0 at t=0) and brings
    every source up together, as a chip does at power-on. Stimuli (pulse, sin, ac) are held at their DC value, so the
    circuit is left alone to settle. Supplies are scaled by vscale. `schedule` {source name (lower case): (start,
    ramp)} powers chosen sources in a sequence instead: held at 0 until `start`, then ramped over their own `ramp`
    (a rail that comes up second or slowly, an enable or reset released after the rails); or ("wave", [[t, level]])
    drives a source with a digital waveform (levels 0 or 1 of its value, EDGE-long edges), e.g. an enable as the
    project's own logic drives it."""
    schedule = schedule or {}
    sup = {s[0].lower() for s in supplies}
    out = []
    depth = 0
    for line in circuit.splitlines():
        p = line.split()
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
        elif low.startswith(".ends"):
            depth -= 1
        # test fixtures far beyond any on-chip value (AC-test feedback inductors, coupling capacitors) are the
        # designer's DC short / open: a power-up transient would otherwise wait on them for hours
        if depth == 0 and len(p) >= 4 and p[0][0].lower() in "lc" and _num(p[3]) is not None and \
                _num(p[3]) >= (1e-6 if p[0][0].lower() == "c" else 1.0):
            out.append(f"R{p[0]} {p[1]} {p[2]} 1m" if p[0][0].lower() == "l" else f"* {line} (open for power-up)")
            continue
        if depth == 0 and len(p) >= 4 and p[0][0].lower() in "vi" and not low.startswith("."):
            x = _dc_value(" ".join(p[3:]))
            if x is not None:
                if p[0].lower() in sup:
                    x *= vscale
                s = schedule.get(p[0].lower(), (0.0, ramp))
                if s[0] == "wave":
                    pts, lvl, last = ["0 0"], 0, 0.0
                    for t, b in s[1]:
                        if b != lvl:
                            t = max(t, last + EDGE)        # PWL times must increase
                            pts += [f"{t:.9g} {lvl * x:.6g}", f"{t + EDGE:.9g} {b * x:.6g}"]
                            lvl, last = b, t + EDGE
                    pts = " ".join(pts)
                else:
                    t0, rr = s
                    pts = f"0 0 {t0:.4g} 0 {t0 + rr:.4g} {x:.6g}" if t0 > 0 else f"0 0 {rr:.4g} {x:.6g}"
                line = f"{p[0]} {p[1]} {p[2]} DC {x:.6g} PWL({pts})"
        out.append(line)
    return "\n".join(out)


def _sched_end(ramp, schedule):
    """When the last scheduled source has settled: the hold of a sequenced power-up starts there."""
    ends = [s[1][-1][0] + EDGE if s[0] == "wave" and s[1] else s[0] + s[1] for s in (schedule or {}).values()
            if s[0] != "wave" or s[1]]
    return max([ramp] + ends)


# time-step ladder: the default step, then 2 ns and 1 ns maximum steps. Two coarse steps can agree on a wrong state
# (TT08 bgr_agolmanesh at tt, 27 C: 80 ns and 16 ns both said 0.31 V, 2 ns and 1 ns 0.525 V), so a result is only
# accepted against a fine step: the default must match 2 ns, or 2 ns must match 1 ns.
STEPS = (None, 2e-9, 1e-9)


def _same(a, b, vtol=0.02, itol=0.05):
    """Two power-up results agree: settled supply current within itol (or 0.1 uA) and every node within vtol."""
    if not a or not b:
        return False
    if abs(a["i_end"] - b["i_end"]) > max(itol * max(abs(a["i_end"]), abs(b["i_end"])), 1e-7):
        return False
    return all(abs(a["nodes"][n][1] - b["nodes"][n][1]) <= vtol for n in a["nodes"]
               if n in b["nodes"] and a["nodes"][n][1] is not None and b["nodes"][n][1] is not None)


def startup_checked(tb, corner, temps, vscale=1.0, ramp=20e-6, settle=30e-6, timeout=600, schedule=None):
    """startup_corner, with every result confirmed against a finer time step. A power-up from 0 V can land in different
    states depending on the integrator's step (a circuit with several states and nothing choosing between them); a
    result counts only when two successive steps of the ladder STEPS agree, and records the step (r["tmax"]). When no
    two agree the condition reports an error naming the values seen: undetermined, never a pass or a fail."""
    stop = _sched_end(ramp, schedule) + settle
    seen = {t: [] for t in temps}
    final = {}
    todo = list(temps)
    for level in STEPS:
        if not todo:
            break
        tmax = level
        res = startup_corner(tb, corner, todo, vscale, ramp, settle, timeout * (1 if level is None else 4), schedule,
                             tmax=tmax)
        nxt = []
        for t in todo:
            r, e = res.get(t, (None, "did not complete"))
            prev = seen[t][-1] if seen[t] else None
            seen[t].append((r, e, tmax))
            if prev and not prev[1] and not e and _same(prev[0], r):
                final[t] = (dict(r, tmax=tmax, step_check=f"agrees at {fmt_step(prev[2] or stop / 4000)} and "
                                                          f"{fmt_step(tmax)}"), None)
            else:
                nxt.append(t)
        todo = nxt
    for t in todo:
        vals = ", ".join(("error" if e else f"{r['i_end'] * 1e6:.3g} \u00b5A") + f" at {fmt_step(tm or stop / 4000)}"
                         for r, e, tm in seen[t])
        final[t] = (None, f"undetermined: the power-up result changes with the simulator's time step ({vals})")
    return final


def fmt_step(s):
    return f"{s * 1e9:.3g} ns"


def startup_corner(tb, corner, temps, vscale=1.0, ramp=20e-6, settle=30e-6, timeout=600, schedule=None, tmax=None):
    """{temp: (result, err)} for one corner and supply scale, in ONE ngspice session.

    At each temperature: the operating point (the state the designer's .op reports), then a transient from an unpowered
    circuit (`uic`, every node at 0 V) with every source ramped over `ramp`, held for `settle`. result holds, for the
    total supply current and every named node, the operating-point value and the value averaged over the last 20 % of
    the hold. The designer's .ic lines are dropped: initial conditions would place the circuit in its working state
    and hide exactly the failure this test looks for (.nodeset only guides the operating point and is kept).
    `schedule` (see _ramped) sequences chosen sources; the hold then starts when the last of them is up."""
    sup = tb.supplies()
    if not sup:
        return {t: (None, "no supply source found") for t in temps}
    circ = _ramped(tb.circuit, ramp, vscale, sup, schedule)
    ramp = _sched_end(ramp, schedule)
    t2 = Testbench(sch=tb.sch, circuit=circ, analyses=tb.analyses,
                   params=[p for p in tb.params if not re.match(r"(?i)^\s*\.ic\b", p)], options=tb.options)
    nets = [n for n in output_nets(tb) if "[" not in n][:40]
    stop = ramp + settle
    t0, tm = ramp + 0.6 * settle, ramp + 0.8 * settle
    # the circuit's total drive: every top-level voltage source, independent or controlled (testbenches often
    # deliver bias through E / H sources or ammeters rather than the supply pins)
    srcs, depth = [], 0
    for line in tb.circuit.splitlines():
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
        elif low.startswith(".ends"):
            depth -= 1
        elif depth == 0 and low[:1] in ("v", "e", "h") and len(low.split()) >= 3:
            # a 0 V source (a ground tie or an ammeter) carries current another source already counts
            if low[0] == "v" and len(low.split()) >= 4 and _dc_value(" ".join(low.split()[3:])) == 0:
                continue
            srcs.append(low.split()[0])
    isup = [f"{n}#branch" for n in dict.fromkeys(srcs)][:40]
    tmp = tempfile.mkdtemp()
    lines = ["set wr_vecnames", "set wr_singlescale"]
    for i, t in enumerate(temps):
        lines.append(f"option temp={t}")
        lines.append("op")
        lines.append(f"echo KAAVAL_OP {i}")
        for v in isup + [f"v({n})" for n in nets]:
            lines.append(f"print {v}")
        # no `uic`: the transient's own starting point is the operating point with every source at its t=0 value (0),
        # a consistent unpowered circuit; `uic` would start from an inconsistent state and can settle anywhere
        lines.append(f"tran {stop / 4000:.4g} {stop:.4g}" + (f" 0 {tmax:.4g}" if tmax else ""))
        lines.append(f"echo KAAVAL_TR {i}")
        lines.append(f"wrdata {tmp}/end{i}.txt all")
        for k, v in enumerate(isup + [f"v({n})" for n in nets]):
            lines.append(f"meas tran kv{k} avg {v} from={tm:.4g} to={stop:.4g}")
            lines.append(f"meas tran kw{k} avg {v} from={t0:.4g} to={tm:.4g}")
            lines.append(f"meas tran kp{k} pp {v} from={tm:.4g} to={stop:.4g}")
    out, err = run(deck(t2, corner, 27, 1.0, control="\n".join(lines)), timeout=timeout)
    if err:
        return {t: (None, err) for t in temps}
    keys = isup + [f"v({n})" for n in nets]
    res = {}
    blocks = re.split(r"^KAAVAL_(OP|TR) (\d+)\s*$", out, flags=re.M)
    got = {}
    for j in range(1, len(blocks) - 2, 3):
        got[(blocks[j], int(blocks[j + 1]))] = blocks[j + 2]
    for i, t in enumerate(temps):
        op_txt, tr_txt = got.get(("OP", i)), got.get(("TR", i))
        if op_txt is None or tr_txt is None:
            res[t] = (None, "did not complete")
            continue
        if re.search(r"(?i)timestep too small|simulation\(s\) aborted", tr_txt):
            res[t] = (None, "the power-up transient did not converge")
            continue
        opv = {}
        for k in keys:
            m = re.search(re.escape(k) + r"\s*=\s*([-+0-9.eE]+)", op_txt, re.I)
            opv[k] = float(m.group(1)) if m else None
        trv, prev, swing = {}, {}, {}
        for idx, k in enumerate(keys):
            m = re.search(rf"^kv{idx}\s*=\s*([-+0-9.eE]+)", tr_txt, re.M | re.I)
            trv[k] = float(m.group(1)) if m else None
            m = re.search(rf"^kw{idx}\s*=\s*([-+0-9.eE]+)", tr_txt, re.M | re.I)
            prev[k] = float(m.group(1)) if m else None
            m = re.search(rf"^kp{idx}\s*=\s*([-+0-9.eE]+)", tr_txt, re.M | re.I)
            swing[k] = float(m.group(1)) if m else None
        isum = lambda d: sum(abs(d[k]) for k in isup if d.get(k) is not None)
        # a transient that left the physical range (nodes far beyond the supplies) diverged numerically: no result
        vmax = max(abs(x[2]) * vscale for x in sup) or 1.8
        if any(v is not None and not (-0.5 <= v <= 1.5 * vmax) for v in list(trv.values())[len(isup):]):
            res[t] = (None, "the power-up transient diverged (node voltages outside the supply range)")
            continue
        # a node still moving between the two windows has not settled; its end value proves nothing yet
        moving = [k[2:-1] for k in keys[len(isup):] if trv[k] is not None and prev[k] is not None and
                  abs(trv[k] - prev[k]) > 0.01]
        osc = {k[2:-1]: swing[k] for k in keys[len(isup):] if swing.get(k) is not None and swing[k] > 0.05}
        if osc:
            # a swing must survive a stiffer integration method and a 5x finer step to count: trapezoidal ringing and
            # step-size artefacts do not
            k0 = max(osc, key=osc.get)
            ctl = (f"option temp={t}\noption method=gear\ntran {stop / 20000:.4g} {stop:.4g}\n"
                   f"meas tran kq pp v({k0}) from={tm:.4g} to={stop:.4g}")
            o4, e4 = run(deck(t2, corner, t, 1.0, control=ctl), timeout=timeout)
            m = re.search(r"^kq\s*=\s*([-+0-9.eE]+)", o4 or "", re.M)
            if not m or abs(float(m.group(1)) - osc[k0]) > 0.3 * osc[k0]:
                osc = {}
                moving = moving or [k0]           # unresolved: neither a verified swing nor a settled state
        r = dict(i_op=isum(opv), i_end=isum(trv), i_prev=isum(prev), nodes={k[2:-1]: (opv[k], trv[k]) for k in keys[len(isup):]},
                 moving=moving, swing=osc, ramp=ramp, settle=settle,
                 op_clean=not re.search(r"(?i)stepping failed|singular matrix", op_txt), confirmed=False)
        # a settled power-up state that differs from the DC answer is checked as a DC solution in its own right: the
        # DC solver, seeded with every node's power-up value, must stay there. Capacitors are open in DC, so states
        # held up only by huge capacitors or inductors (AC-test tricks), and high-gain outputs that drifted to a rail,
        # fall back to the one true solution and are not reported
        diff = any(a is not None and b is not None and abs(a - b) > 0.1 for a, b in r["nodes"].values())
        if diff and not moving and not osc and r["op_clean"]:
            end = _last_row(os.path.join(tmp, f"end{i}.txt"))
            if end:
                ns = ".nodeset " + " ".join(f"v({k})={v:.6g}" for k, v in end.items())
                t3 = Testbench(sch=t2.sch, circuit=t2.circuit, analyses=t2.analyses, params=t2.params + [ns],
                               options=t2.options)
                o3, e3 = run(deck(t3, corner, t, 1.0, control="op\n" + "\n".join(f"print {v}" for v in keys)),
                             timeout=120)
                seeded = {}
                for k in keys:
                    m = re.search(re.escape(k) + r"\s*=\s*([-+0-9.eE]+)", o3 or "", re.I)
                    seeded[k] = float(m.group(1)) if m else None
                r["confirmed"] = all(seeded[k] is not None and abs(seeded[k] - trv[k]) < 0.05
                                     for k in keys[len(isup):] if trv[k] is not None)
        res[t] = (r, None)
    shutil.rmtree(tmp, ignore_errors=True)
    return res


def _last_row(path):
    """{vector: value} at the last time point of a `wrdata ... all` file (node voltages only)."""
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    hdr, last = lines[0].split(), lines[-1].split()
    out = {}
    for h, v in zip(hdr, last):
        if h == "time" or "#" in h or h.startswith("@") or "(" in h:
            continue
        try:
            out[h] = float(v)
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------- stability: loop gain at a break point
MOS_PIN = {"d": 1, "g": 2, "s": 3, "b": 4}


def break_net(circuit, net, pins):
    """Split `net` for a loop-gain probe: the listed element pins ('XM2.g', 'R3.1', 'X1.3') move to a new node
    `kv_brk_x`; everything else stays on `net` (renamed side y). Returns the new circuit and the two node names, or
    raises ValueError naming what was not found. Only top-level elements are touched."""
    want = {}
    for p in pins:
        el, _, pin = p.rpartition(".")
        want.setdefault(el.lower(), set()).add(pin.lower())
    out, depth, moved = [], 0, 0
    for line in circuit.splitlines():
        low = line.strip().lower()
        if low.startswith(".subckt"):
            depth += 1
        elif low.startswith(".ends"):
            depth -= 1
        p = line.split()
        if depth == 0 and p and p[0].lower() in want:
            for pin in want[p[0].lower()]:
                k = MOS_PIN.get(pin) if p[0][0].lower() in "mx" and pin in MOS_PIN else (int(pin) if pin.isdigit() else None)
                if k is None or k >= len(p) or p[k].lower() != net.lower():
                    raise ValueError(f"{p[0]} pin {pin} is not on net {net}")
                p[k] = "kv_brk_x"
                moved += 1
            line = " ".join(p)
        out.append(line)
    if moved != sum(len(v) for v in want.values()):
        raise ValueError("some break pins were not found among the cell's top-level elements")
    return "\n".join(out) + f"\nVkvz kv_brk_x {net} dc 0 ac 0\nIkvz 0 kv_brk_x dc 0 ac 0", "kv_brk_x", net


def loopgain_corner(tb, corner, conds, fstart=1.0, fstop=10e9, ppd=20, timeout=600):
    """{(temp, vscale): (result, err)}: loop gain T(f) at the break (Tian's method: T = (Y12 + Y21) / (Y11 + Y22) of
    the two-port seen at the cut, from one series-voltage and one shunt-current injection), with unity-gain frequency,
    phase margin and gain margin, at each condition of one corner, in one ngspice session."""
    sup = tb.supplies()
    tmp = tempfile.mkdtemp()
    lines = ["set wr_vecnames", "set wr_singlescale"]
    for i, (t, v) in enumerate(conds):
        lines.append(f"option temp={t}")
        for name, _, val in sup:
            lines.append(f"alter {name.lower()} dc={val * v:.6g}")
        lines += ["alter @vkvz[acmag]=1", "alter @ikvz[acmag]=0", f"ac dec {ppd} {fstart:g} {fstop:g}",
                  f"wrdata {tmp}/a{i}.txt v(kv_brk_x) v({tb.brk_y}) i(vkvz)",
                  "alter @vkvz[acmag]=0", "alter @ikvz[acmag]=1", f"ac dec {ppd} {fstart:g} {fstop:g}",
                  f"wrdata {tmp}/b{i}.txt v(kv_brk_x) i(vkvz)", f"echo KAAVAL_LG {i}"]
    out, err = run(deck(tb, corner, 27, 1.0, control="\n".join(lines)), timeout=timeout)
    res = {}
    for i, c in enumerate(conds):
        pa, pb = os.path.join(tmp, f"a{i}.txt"), os.path.join(tmp, f"b{i}.txt")
        if err or not (os.path.exists(pa) and os.path.exists(pb)):
            res[c] = (None, err or "the AC analysis did not run")
            continue
        A = [list(map(float, l.split())) for l in open(pa).read().splitlines()[1:] if l.strip()]
        B = [list(map(float, l.split())) for l in open(pb).read().splitlines()[1:] if l.strip()]
        f, T = [], []
        for ra, rb in zip(A, B):
            vxA, vyA, iz = complex(ra[1], ra[2]), complex(ra[3], ra[4]), complex(ra[5], ra[6])
            vB, izB = complex(rb[1], rb[2]), complex(rb[3], rb[4])
            ixA, iyA, ixB, iyB = -iz, iz, 1 - izB, izB
            try:
                s1, s2 = ixB / vB, iyB / vB
                y11 = (ixA - s1 * vyA) / (vxA - vyA)
                y21 = (iyA - s2 * vyA) / (vxA - vyA)
                T.append(((s1 - y11) + y21) / (y11 + (s2 - y21)))
                f.append(ra[0])
            except ZeroDivisionError:
                continue
        res[c] = (_margins(f, T), None) if len(T) > 3 else (None, "no loop gain (is the break on the loop?)")
    shutil.rmtree(tmp, ignore_errors=True)
    return res


def _margins(f, T):
    """Unity-gain frequency, phase margin and gain margin from T(f), phase unwrapped from DC."""
    import cmath, math
    mag = [20 * math.log10(max(abs(t), 1e-30)) for t in T]
    ph, prev, off = [], None, 0.0
    for t in T:
        p = math.degrees(cmath.phase(t))
        if prev is not None:
            while p + off - prev > 180:
                off -= 360
            while p + off - prev < -180:
                off += 360
        ph.append(p + off)
        prev = ph[-1]
    r = dict(dc_gain_db=mag[0], dc_phase=ph[0], ugf=None, pm=None, gm_db=None, pcf=None,
             f=f[::2], mag=[round(m, 2) for m in mag[::2]], phase=[round(p, 1) for p in ph[::2]])
    # a negative-feedback loop starts near 0 deg; one that starts near +-180 is positive feedback at DC
    ref = 0.0 if abs(ph[0]) < 90 else (180.0 if ph[0] > 0 else -180.0)
    for k in range(1, len(T)):
        if r["ugf"] is None and mag[k - 1] >= 0 > mag[k]:
            a = mag[k - 1] / (mag[k - 1] - mag[k])
            r["ugf"] = f[k - 1] * (f[k] / f[k - 1]) ** a
            r["pm"] = 180.0 + (ph[k - 1] + a * (ph[k] - ph[k - 1]) - ref)
        if r["pcf"] is None and (ph[k - 1] - ref) > -180 >= (ph[k] - ref):
            a = (-180 - (ph[k - 1] - ref)) / ((ph[k] - ref) - (ph[k - 1] - ref))
            r["pcf"] = f[k - 1] * (f[k] / f[k - 1]) ** a
            r["gm_db"] = -(mag[k - 1] + a * (mag[k] - mag[k - 1]))
    r["positive_dc"] = ref != 0.0
    return r


# ---------------------------------------------------------------- the bench's tools: health and waveforms
def health():
    """What this engine actually runs: ngspice version and whether the sky130 models are installed."""
    try:
        out = subprocess.run(["ngspice", "-v"], capture_output=True, text=True, timeout=20).stdout
        m = re.search(r"ngspice-(\d+)", out)
        ver = f"ngspice-{m.group(1)}" if m else None
    except (OSError, subprocess.TimeoutExpired):
        ver = None
    return dict(ngspice=ver, pdk="sky130" if os.path.exists(PDK_LIB) else None, ok=bool(ver and os.path.exists(PDK_LIB)))


def powerup_wave(tb, corner, temp, vscale=1.0, ramp=20e-6, settle=300e-6, nets=None, points=400, schedule=None,
                 tmax=2e-9):
    """One power-up from 0 V at one condition: time series of the total source current and the cell's named nodes,
    for the bench's waveform view. Same deck as startup_corner (all sources ramp, stimuli held at DC; `schedule`
    sequences chosen sources, see _ramped)."""
    sup = tb.supplies()
    circ = _ramped(tb.circuit, ramp, vscale, sup, schedule)
    ramp = _sched_end(ramp, schedule)
    t2 = Testbench(sch=tb.sch, circuit=circ, analyses=tb.analyses,
                   params=[p for p in tb.params if not re.match(r"(?i)^\s*\.ic\b", p)], options=tb.options)
    nets = [n for n in (nets or output_nets(tb)) if "[" not in n][:8]
    srcs = [s[0].lower() for s in sup]
    stop = ramp + settle
    tmp = tempfile.mkdtemp()
    vecs = " ".join([f"{s}#branch" for s in srcs] + [f"v({n})" for n in nets])
    ctl = (f"set wr_vecnames\nset wr_singlescale\noption temp={temp}\noption method=gear\n"
           f"tran {stop / 4000:.4g} {stop:.4g}" + (f" 0 {tmax:.4g}" if tmax else "") + "\n"
           f"linearize {vecs}\nwrdata {tmp}/w.txt {vecs}")
    out, err = run(deck(t2, corner, 27, 1.0, control=ctl), timeout=300)
    p = os.path.join(tmp, "w.txt")
    if err or not os.path.exists(p):
        shutil.rmtree(tmp, ignore_errors=True)
        return None, err or "the transient did not run"
    rows = [l.split() for l in open(p).read().splitlines()[1:] if l.strip()]
    shutil.rmtree(tmp, ignore_errors=True)
    step = max(1, len(rows) // points)
    rows = rows[::step]
    t = [float(r[0]) for r in rows]
    i = [sum(abs(float(r[1 + k])) for k in range(len(srcs))) for r in rows]
    v = {n: [float(r[1 + len(srcs) + k]) for r in rows] for k, n in enumerate(nets)}
    return dict(t=t, i=i, v=v, corner=corner, temp=temp, vscale=vscale), None

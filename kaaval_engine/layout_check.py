"""layout_check.py — does the layout build the circuit the designer simulated?

A designer simulates the schematic; the fab builds the layout. A cell drawn both ways (xschem `<cell>.sch` and Magic
`<cell>.mag`) is compared the way sign-off LVS does it: Magic extracts the layout's devices and connectivity
(extract.cell), our netlister writes the schematic as the same subcircuit, and Netgen, the open LVS tool, matches the
two with the sky130 setup (device classes, permutable pins, parallel devices merged). A mismatch means the chip will
not be the circuit that was simulated: a missing or extra device, a wrong size, a wire to the wrong net, a port the
layout does not have.

Netgen and Magic run our own commands in a temporary folder; the repository's scripts are never read or run.

    for c in pairs(root):
        r = compare(root, c)          # {cell, match: True / False / None, summary: [...], error}
"""
import os, re, shutil, subprocess, tempfile

from kaaval_engine import extract, stdcells
from kaaval_engine import netlist as N
from kaaval_engine.paths import PDK_ROOT

SETUP = os.path.join(PDK_ROOT, "libs.tech", "netgen", "sky130A_setup.tcl")


def available():
    return extract.available() and bool(shutil.which("netgen")) and os.path.isfile(SETUP)


def pairs(root):
    """[{cell, sch, sym, mag}] for every cell the repository draws both as a schematic (with its symbol) and as a
    layout, relative paths. One entry per cell name (the first schematic and layout found)."""
    sch, mag = {}, {}
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in sorted(fs):
            base, ext = os.path.splitext(f)
            rel = os.path.relpath(os.path.join(d, f), root)
            if ext == ".sch" and os.path.isfile(os.path.join(d, base + ".sym")):
                sch.setdefault(base, rel)
            elif ext == ".mag":
                mag.setdefault(base, rel)
    return [dict(cell=c, sch=sch[c], sym=os.path.splitext(sch[c])[0] + ".sym", mag=mag[c])
            for c in sorted(set(sch) & set(mag))]


TOK = re.compile(r"""\S+?='[^']*'|\S+?="[^"]*"|\S+""")        # a quoted parameter value is one token


def flatten(text, top):
    """`.subckt top` with every instance of a sub-circuit defined in `text` expanded, recursively, down to the PDK's
    primitive devices: one transistor-level cell, so the comparison does not depend on how either view names its
    hierarchy. Instance paths join with '/', internal nets are prefixed by their instance path."""
    subs, cur, body = {}, None, []
    lines = []
    glob = {g.lower() for line in text.splitlines() if line.lower().startswith(".global") for g in line.split()[1:]}
    for raw in text.splitlines():                          # join '+' continuations
        if raw.startswith("+") and lines:
            lines[-1] += " " + raw[1:]
        else:
            lines.append(raw)
    for line in lines:
        t = TOK.findall(line)
        if not t or t[0].startswith("*"):
            continue
        if t[0].lower() == ".subckt":
            cur = t[1].lower()
            ports = [x for x in t[2:] if "=" not in x]
            subs[cur] = (ports, [])
            continue
        if t[0].lower().startswith(".ends"):
            cur = None
            continue
        if cur and not t[0].startswith("."):
            subs[cur][1].append(t)
    if top.lower() not in subs:
        return None
    out = []

    def walk(name, nets, path, depth):
        ports, elems = subs[name]
        m = {p.lower(): n for p, n in zip(ports, nets)}
        net = lambda x: m.get(x.lower(), x if x.lower() in glob or not path else f"{path}{x}")   # (.GLOBAL: one net)
        for t in elems:
            if t[0][:1].lower() == "x":
                args = [x for x in t[1:] if "=" not in x]
                params = [x for x in t[1:] if "=" in x]
                sub = args[-1].lower()
                if sub in subs and depth < 30:
                    walk(sub, [net(x) for x in args[:-1]], f"{path}{t[0]}/", depth + 1)
                    continue
                out.append(" ".join([f"{path}{t[0]}" if path else t[0]] + [net(x) for x in args[:-1]] + [args[-1]] +
                                    params))
                continue
            k = {"m": 4, "q": 3, "d": 2, "r": 2, "c": 2, "l": 2}.get(t[0][:1].lower(), 2)
            out.append(" ".join([f"{path}{t[0]}" if path else t[0]] + [net(x) for x in t[1:1 + k]] + t[1 + k:]))
    ports = subs[top.lower()][0]
    walk(top.lower(), ports, "", 0)
    return f".subckt {top} {' '.join(ports)}\n" + "\n".join(out) + f"\n.ends {top}\n"


PRIMITIVE = re.compile(r"(?i)^(sky130_fd_pr__|gf180mcu_fd_pr__)\w+$")


def unresolved(flat):
    """Cells the flattened schematic still instantiates without a definition (a symbol from a library outside the
    repository): their devices are missing from our side, so the comparison cannot be judged."""
    out = set()
    for line in flat.splitlines():
        t = [x for x in TOK.findall(line) if "=" not in x]
        if t and t[0][:1].lower() == "x" and len(t) > 2 and not PRIMITIVE.match(t[-1]) and \
                not re.fullmatch(r"(?i)[-+.\d]+[a-z]*", t[-1]):                  # (a value, not a cell)
            out.add(t[-1])
    return sorted(out)


def schematic_subckt(root, pair):
    """The schematic as `.subckt <cell> <ports>` (its sub-circuits first), the way xschem writes a cell."""
    p = os.path.join(root, pair["sch"])
    text = "\n".join(N._subckt(p, pair["cell"], N.symbol(os.path.join(root, pair["sym"])), {})) + "\n"
    # standard cells the schematic only names (the layout extraction holds their transistors): their PDK definitions;
    # then flat, like the layout's extraction (extract.cell flat=True)
    full = stdcells.defs_for(text) + "\n" + text
    return flatten(full, pair["cell"]) or full


def sizes(text):
    """'M1: w 1 in the layout, 2 in the schematic' for each property Netgen found different."""
    out, dev = [], ""
    for line in text.splitlines():
        m = re.match(r"^(\S+) vs\. (\S+):\s*$", line.strip())
        if m:
            dev = m.group(2).split(":")[-1] or m.group(1)
            continue
        m = re.match(r"^(\w+) circuit1: (\S+)\s+circuit2: (\S+)", line.strip())
        if m and dev and len(out) < 20:
            out.append(f"{dev}: {m.group(1)} {m.group(2)} in the layout, {m.group(3)} in the schematic")
    return out


def size_delta(line):
    """The relative difference a sizes() line states (0.66 for w 1 against 2), or None."""
    m = re.search(r"(\S+) in the layout, (\S+) in the schematic", line)
    try:
        a, b = float(m.group(1)), float(m.group(2))
    except (AttributeError, ValueError):
        return None
    return abs(a - b) / max(abs(a), abs(b)) if max(abs(a), abs(b)) else 0.0


BIG = 0.05                       # a size more than 5 % off is a warning; less is noted (end effects, rounding)


def _summary(text):
    """The lines of a Netgen report that say what differs (counts, unmatched nets and devices, pin mismatches)."""
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if re.search(r"(?i)\*\*mismatch\*\*|mismatch|no matching|unmatched|failed pin|does not match|"
                     r"property errors|^\s*instance:|net:", s) and len(keep) < 40:
            keep.append(s)
    return keep


ROW = re.compile(r"^(\S+) \((\d+)(?:->(\d+))?\)$")
VT = re.compile(r"(?i)_(lvt|hvt|mvt)\b")


def family(model):
    """A device model with the PDK's fixed-size variant suffix removed (res_xhigh_po_0p35 is res_xhigh_po drawn at
    0.35 um): the same device, so never a mismatch. A different threshold flavour (_lvt / _hvt) or resistor type
    (high_po / xhigh_po) stays a different family."""
    return re.sub(r"(?i)_0p\d+$", "", model.strip().lower())


def counts(text):
    """{model family: [layout devices, schematic devices]} from a Netgen report's device-class table, after Netgen's
    own merging of parallel and series devices (the number after '->'). Only the last table (the top cell) counts."""
    tables, cur = [], None
    for line in text.splitlines():
        if "|" not in line:
            if cur:
                tables.append(cur)
                cur = None
            continue
        left, right = (re.sub(r"\*\*Mis\w*\**", "", x).strip() for x in line.split("|", 1))   # (often cut: **Mismat)
        got = False
        for side, cell in ((0, left), (1, right)):
            m = ROW.match(cell)
            if m and "sky130_fd_pr__" in m.group(1):
                cur = cur or {}
                cur.setdefault(family(m.group(1)), [0, 0])[side] += int(m.group(3) or m.group(2))
                got = True
        if not got and cur and not re.match(r"(?i)\(no matching", left + right) and not left.startswith("Number"):
            pass
    if cur:
        tables.append(cur)
    return tables[-1] if tables else {}


def differences(c):
    """Findings from {family: [layout, schematic]}: a family drawn in one view and absent from the other with the same
    device kind present instead is a flavour change (threshold voltage or resistor type); otherwise counts differ."""
    out = []
    only_l = {f: n[0] for f, n in c.items() if n[0] and not n[1]}
    only_s = {f: n[1] for f, n in c.items() if n[1] and not n[0]}
    kind = lambda f: re.sub(r"(?i)_(lvt|hvt|mvt)$", "", re.sub(r"(?i)(x?high_po|low_po).*$", "po", f))
    for fl, nl in sorted(only_l.items()):
        for fs, ns in sorted(only_s.items()):
            if kind(fl) == kind(fs) and fs in only_s and fl in only_l:
                out.append(dict(kind="flavour", layout=fl, schematic=fs, n_layout=nl, n_schematic=ns))
                only_l.pop(fl, None), only_s.pop(fs, None)
                break
    for f, (nl, ns) in sorted(c.items()):
        if f in only_l or f in only_s or (nl and ns and nl != ns):
            if not any(f in (d["layout"], d["schematic"]) for d in out if d["kind"] == "flavour"):
                out.append(dict(kind="count", model=f, n_layout=nl, n_schematic=ns))
    return out


GND = re.compile(r"(?i)^(v?ss\w*|vgnd|gnd|agnd|dgnd|vsubs|0)$")
SUP = re.compile(r"(?i)^(v?dd\w*|vpwr|vdpwr|vapwr|vcc\w*|avdd|dvdd)$")


def off_devices(text):
    """{model family: transistors that do nothing by construction}, the dummies a layout adds beside matched devices:
    drain and source on one net; an n-device whose gate is on a ground net, or a p-device whose gate is on a supply
    net; or one whose drain and source nets drive nothing (no gate anywhere, not a port of the cell: an unused cell
    such as a dummy inverter)."""
    devs, gates, ports = [], set(), set()
    for line in text.splitlines():
        t = [x for x in line.split() if "=" not in x]
        if t and t[0].lower() == ".subckt":
            ports = set(t[2:])
        if len(t) < 6 or t[0][:1].lower() not in "xm":
            continue
        devs.append((family(t[5]), t[1], t[2], t[3]))
        gates.add(t[2])
    rail = lambda n: GND.match(n.split("/")[-1]) or SUP.match(n.split("/")[-1])
    idle = lambda n: rail(n) or (n not in gates and n not in ports)
    out = {}
    for model, d, g, s in devs:
        gn = g.split("/")[-1]
        if d == s or (re.search(r"__nfet", model) and GND.match(gn)) or (re.search(r"__pfet", model) and SUP.match(gn)) \
                or (idle(d) and idle(s)):
            out[model] = out.get(model, 0) + 1
    return out


def compare(root, pair, timeout=300):
    """Netgen LVS of the cell's extracted layout against its schematic."""
    out = dict(cell=pair["cell"], sch=pair["sch"], mag=pair["mag"], match=None, summary=[], error=None)
    if not available():
        out["error"] = "Magic, Netgen or the sky130 Netgen setup is not installed on this server"
        return out
    try:
        sch = schematic_subckt(root, pair)
    except Exception as e:                                  # noqa: BLE001 - a schematic we cannot read is reported
        out["error"] = f"the schematic could not be netlisted: {e}"
        return out
    missing = unresolved(sch)
    if missing:
        out["verdict"] = "schematic incomplete"
        out["error"] = (f"the schematic uses {len(missing)} cell(s) Kaaval could not resolve to devices "
                        f"({', '.join(missing[:5])}), so it is not compared")
        return out
    lay, err = extract.cell(root, pair["cell"], pair["mag"], timeout, flat=True)
    if not lay:
        out["error"] = err
        return out
    devices = lambda t: sum(1 for l in t.splitlines() if l[:1] and l[:1].lower() in "xmrcdq")
    if not devices(lay):                              # metal and labels only: an abstract or placeholder view
        out["verdict"] = "layout has no devices"
        out["error"] = "the layout cell holds no devices (an abstract or placeholder view), so it is not compared"
        return out
    with tempfile.TemporaryDirectory(prefix="kaaval_lvs_") as t:
        open(os.path.join(t, "layout.spice"), "w").write(lay)
        open(os.path.join(t, "schematic.spice"), "w").write(sch)
        try:
            p = subprocess.run(["netgen", "-batch", "lvs", f"layout.spice {pair['cell']}",
                                f"schematic.spice {pair['cell']}", SETUP, "report.txt"], cwd=t, capture_output=True,
                               text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            out["error"] = f"Netgen took over {timeout} s"
            return out
        rep = os.path.join(t, "report.txt")
        text = open(rep, errors="replace").read() if os.path.isfile(rep) else ""
        log = p.stdout + p.stderr
    final = re.search(r"Final result:\s*(.+)", text + "\n" + log)
    if not final:
        out["error"] = "Netgen gave no result (" + " ".join(log.split()[-25:]) + ")"
        return out
    res = final.group(1).strip()
    out["result"] = res
    out["match"] = bool(re.fullmatch(r"(?i)circuits match uniquely\.?", res))
    if re.search(r"(?i)property errors were found|with property errors", text + res):
        out["verdict"] = "sizes differ"                  # the same circuit, with devices of other sizes (W, L, value)
        out["sizes"] = sizes(text)
        return out
    if not out["match"] and re.search(r"(?i)failed pin matching", res) and \
            re.search(r"(?i)^Netlists match uniquely( with [a-z ]*errors)?\.?\s*$", text, re.M):
        out["verdict"] = "match, ports differ"              # the same circuit inside; its ports are named or wired otherwise
        out["ports"] = [l.strip() for l in text.splitlines()
                        if re.search(r"(?i)no matching pin|no connects|tied together|disagree on pin", l)][:12]
        if re.search(r"(?i)property errors", text):
            out["sizes"] = sizes(text)
        return out
    if not out["match"]:
        out["summary"] = _summary(text)
        out["diffs"] = differences(counts(text))
        lo, so = off_devices(lay), off_devices(sch)
        for d in out["diffs"]:                         # extra layout devices that are all off: dummies, said so
            if d["kind"] == "count" and d["n_schematic"] and d["n_layout"] > d["n_schematic"]:
                extra = lo.get(d["model"], 0) - so.get(d["model"], 0)
                if extra >= d["n_layout"] - d["n_schematic"]:
                    d["dummies"] = True
        # devices differ: the chip is not the circuit simulated. Otherwise only pins or nets could not be matched
        # (a label, the substrate's implicit VSUBS): reported, never judged as a layout error
        out["verdict"] = "devices differ" if out["diffs"] else "pins or nets only"
    else:
        out["verdict"] = "match"
    return out


def _short(model):
    return re.sub(r"(?i)^sky130_fd_pr__", "", model)


def finding(r):
    """One review finding for a cell whose layout and schematic hold different devices, or None."""
    if r.get("verdict") == "sizes differ":
        ds = [d for d in map(size_delta, r.get("sizes", [])) if d is not None]
        big = any(d > BIG for d in ds)
        worst = max(ds) if ds else None
        return dict(rule="layout/sizes_differ", severity="warn" if big or not ds else "info", device=r["cell"],
                    title=(f"{r['cell']}: the committed layout draws devices at other sizes than its schematic (Netgen LVS: the same "
                           f"circuit, with property errors" + (f"; up to {worst * 100:.0f} % off" if ds else "") +
                           "): " + "; ".join(r.get("sizes", [])[:4]))[:600],
                    location=f"{r['mag']} vs {r['sch']}", detail=r)
    if r.get("verdict") == "match, ports differ":
        return dict(rule="layout/ports_differ", severity="info", device=r["cell"],
                    title=(f"{r['cell']}: the layout is the same circuit as its schematic, but its ports are named or "
                           f"wired otherwise (Netgen LVS: " + "; ".join(r.get("ports", [])[:3]) + "). A port the layout "
                           "leaves unconnected is floating on the chip.")[:700],
                    location=f"{r['mag']} vs {r['sch']}", detail=r)
    if r.get("verdict") != "devices differ":
        return None
    only_dummies = all(d.get("dummies") for d in r["diffs"])
    parts = []
    for d in r["diffs"]:
        if d["kind"] == "flavour":
            what = ("a different threshold voltage" if VT.search(d["layout"] + " " + d["schematic"])
                    else "a different resistor type, so a different resistance" if "_po" in d["layout"]
                    else "a different device")
            parts.append(f"the layout draws {d['n_layout']} {_short(d['layout'])} where the schematic has "
                         f"{d['n_schematic']} {_short(d['schematic'])} ({what})")
        else:
            parts.append(f"{_short(d['model'])}: {d['n_layout']} in the layout, {d['n_schematic']} in the schematic"
                         + (" (the extra ones are off by construction: layout dummies, not in the schematic)"
                            if d.get("dummies") else ""))
    if only_dummies:
        return dict(rule="layout/dummies", severity="info", device=r["cell"],
                    title=(f"{r['cell']}: the layout adds dummy devices the schematic does not have: " + "; ".join(parts)
                           + ". They are off, so the circuit is the one simulated; LVS sign-off needs them in the "
                             "schematic too.")[:600], location=f"{r['mag']} vs {r['sch']}", detail=r)
    return dict(rule="layout/devices_differ", severity="warn", device=r["cell"],
                title=(f"{r['cell']}: the committed layout and schematic hold different devices: " + "; ".join(parts) +
                       " (Netgen LVS, parallel devices merged). Either the chip is not the circuit that was simulated, "
                       "or the schematic is out of date.")[:700],
                location=f"{r['mag']} vs {r['sch']}", detail=r)


def review(root, max_cells=12, budget=240.0):
    """Every cell drawn both ways, compared (up to max_cells, within budget seconds): (results, findings, note)."""
    import time
    if not available():
        return [], [], ""
    ps = pairs(root)
    if not ps:
        return [], [], ""
    t0, res = time.time(), []
    for p in ps[:max_cells]:
        if time.time() - t0 > budget:
            break
        res.append(compare(root, p, timeout=max(10, int(budget - (time.time() - t0)))))
    fs = [f for f in map(finding, res) if f]
    v = lambda k: sum(1 for r in res if r.get("verdict") == k)
    skipped = len(ps) - len(res)
    note = (f"Layout against schematic (Magic extraction, Netgen LVS): {len(ps)} cell(s) drawn both ways; "
            f"{v('match')} match, {v('devices differ')} with different devices, {v('sizes differ')} with different device "
            f"sizes, {v('match, ports differ')} the same circuit with ports named or wired otherwise, {v('schematic incomplete')} not "
            f"judged (cells we could not resolve), {v('layout has no devices')} with an empty layout view, "
            f"{v('pins or nets only')} differ only in "
            f"pin or net names (not judged), {sum(1 for r in res if r['match'] is None)} could not be compared"
            + (f", {skipped} not compared (time)" if skipped else "") + ".")
    return res, fs, note


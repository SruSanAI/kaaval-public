"""netlist.py — SPICE netlist of an xschem schematic, built from the file's TEXT (no xschem, nothing executed).

Connectivity: every wire `N x1 y1 x2 y2 {lab=...}` and every symbol pin (layer-5 box in the .sym, transformed with
xschem's ROTATION) is a point set; points that coincide, or a pin/endpoint lying on a wire, join one net (union-find).
A net takes its name from a wire's lab= (xschem writes these on save) or from a label/port symbol on it; the rest get
net1, net2, ... Each device line is produced from the symbol's own format= string (@name, @pinlist, @model, @W ...)
with the instance attributes over the symbol's template defaults, which is how xschem builds it.

Dropped on purpose: netlist_commands blocks (code.sym / code_shown.sym: .control, .include, shell), launchers and
probes. A testbench therefore comes out as circuit only; analyses and models are added by our own runner. In a
sub-cell, a code block's device lines are kept (code_devices): xschem copies them into the sub-circuit.

    python -m kaaval_engine.netlist path/to/top.sch > top.spice
"""
import functools, os, re, sys

from kaaval_engine.xsch import SYMBOL_PATHS, _block, _props, parse, xform

SKIP_TYPES = {"netlist_commands", "launcher", "probe", "logo", "spice_probe", "ngprobe", "title", "noconn"}
LABEL_TYPES = {"label", "ipin", "opin", "iopin"}


@functools.lru_cache(maxsize=None)
def _repo_index(root):
    """basename -> paths of every .sym/.sch under root (symbols are often referenced by an absolute path from the
    designer's own machine, e.g. /foss/designs/<repo>/xschem/x.sym)."""
    idx = {}
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in fs:
            if f.endswith((".sym", ".sch")):
                idx.setdefault(f, []).append(os.path.join(d, f))
    return idx


def _repo_root(local):
    d = local
    while d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, ".git")) or os.path.exists(os.path.join(d, "info.yaml")):
            return d
        d = os.path.dirname(d)
    return local


def _find_sym(sym, local):
    for d in [local] + SYMBOL_PATHS:
        p = os.path.normpath(os.path.join(d, sym))
        if os.path.exists(p):
            return p
    cands = _repo_index(_repo_root(local)).get(os.path.basename(sym), [])
    if cands:
        # prefer the copy whose path ends like the reference (same parent folder name)
        tail = os.path.join(*sym.replace("\\", "/").split("/")[-2:]) if "/" in sym else sym
        return next((c for c in cands if c.endswith(tail)), cands[0])
    return None


@functools.lru_cache(maxsize=None)
def symbol(path):
    """{type, format, template, pins:[(name, x, y)], subckt?} of a .sym file."""
    text = open(path, errors="replace").read()
    k = re.search(r"^K \{", text, re.M)
    head = _block(text, k.end())[0] if k else ""
    # the K block is brace-quoted: one level of backslash escapes (\\ -> \, \{ -> {) is removed before its
    # attributes are read, as xschem does; inner quotes in a value are then \"
    head = re.sub(r"\\(.)", r"\1", head.replace("\\\\", "\x00")).replace("\x00", "\\")

    def field(key):
        pat = r'(?<![\w])' + key + r'\s*=\s*'
        m = re.search(pat + r'"((?:[^"\\]|\\.)*)"', head, re.S) or re.search(pat + r"(\S+)", head)
        return m.group(1).replace('\\"', '"') if m else ""
    pins = []
    for kind, f, props in parse(text):
        if kind == "B" and f and f[0] == "5":
            x1, y1, x2, y2 = map(float, f[1:5])
            p = _props(props)
            pins.append((p.get("name", ""), (x1 + x2) / 2, (y1 + y2) / 2, p.get("sim_pinnumber")))
    # xschem lists pins in file order; only sim_pinnumber (when every pin has one) reorders them. pinnumber does not.
    if pins and all(q[3] for q in pins):
        try:
            pins.sort(key=lambda q: float(q[3]))
        except ValueError:
            pass
    return dict(type=field("type"), format=field("format").replace("\\\n", " ").replace("\n+", " ").replace("\n", " "),
                template=_props(field("template").replace("\n+", " ")), pins=[(n, x, y) for n, x, y, _ in pins],
                extra=field("extra").split(), glob=field("global").lower() in ("true", "1", "ground"))


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _on_segment(px, py, w, eps=1e-6):
    x1, y1, x2, y2 = w
    if abs((x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)) > eps * max(1.0, abs(x2 - x1) + abs(y2 - y1)):
        return False
    return min(x1, x2) - eps <= px <= max(x1, x2) + eps and min(y1, y2) - eps <= py <= max(y1, y2) + eps


def _key(x, y):
    return (round(x, 3), round(y, 3))


def expand(name):
    """xschem bus notation to bits: 'a[6:1]' or 'a[6..1]' -> a[6] .. a[1]; 'a[0:3]' ascending; comma lists
    concatenate; 'a[2]' or a plain name stay one bit."""
    out = []
    for part in [p for p in str(name).split(",") if p]:
        m = re.fullmatch(r"(.*)\[(\d+)(?::|\.\.)(\d+)\](.*)", part)
        if not m:
            out.append(part)
            continue
        a, b = int(m.group(2)), int(m.group(3))
        rng = range(a, b - 1, -1) if a >= b else range(a, b + 1)
        out += [f"{m.group(1)}[{i}]{m.group(4)}" for i in rng]
    return out or [str(name)]


def build(sch_path, top=True, done=None):
    """List of netlist text blocks (subcircuits first, then this schematic) for sch_path."""
    done = {} if done is None else done
    local = os.path.dirname(os.path.abspath(sch_path))
    items = parse(open(sch_path, errors="replace").read())
    uf, wires, wire_lab, insts, code = _UF(), [], {}, [], []
    for kind, f, props in items:
        if kind == "N":
            w = tuple(map(float, f[:4]))
            wires.append(w)
            a, b = _key(w[0], w[1]), _key(w[2], w[3])
            uf.union(a, b)
            lab = _props(props).get("lab")
            # '#netN' is xschem's own auto-name, saved from its last netlisting: it can be stale and collide with the
            # names we generate, so only a designer's label names a net
            if lab and not lab.startswith("#"):
                wire_lab.setdefault(a, lab)
        elif kind == "C":
            sym = f[0]
            path = _find_sym(sym, local)
            if not path:
                continue
            sd = symbol(path)
            if sd["type"] == "netlist_commands" and not top:
                a = dict(sd["template"], **_props(props))
                if str(a.get("only_toplevel", "false")).strip().lower() not in ("true", "1"):
                    code += code_devices(a.get("value", ""))
                continue
            if sd["type"] in SKIP_TYPES or not sd["format"] and sd["type"] not in LABEL_TYPES:
                continue
            x0, y0, rot, flip = float(f[1]), float(f[2]), int(f[3]), int(f[4])
            a = dict(sd["template"], **_props(props))
            pins = [(n, _key(*xform(x, y, rot, flip, x0, y0))) for n, x, y in sd["pins"]]
            for _, k in pins:
                uf.find(k)
            # the designer switched this element off for simulation (xschem spice_ignore): true drops it, short joins
            # all its pins into one net
            ign = str(a.get("spice_ignore", "")).strip().lower()
            if ign in ("true", "1", "open"):
                continue
            if ign == "short":
                for _, k in pins[1:]:
                    uf.union(pins[0][1], k)
                continue
            insts.append((sym, path, sd, a, pins))
    # pins and wire endpoints that touch a wire's interior join that wire's net
    pts = set(uf.p)
    for w in wires:
        for k in pts:
            if _on_segment(k[0], k[1], w):
                uf.union(_key(w[0], w[1]), k)
    names = {}
    for k, lab in wire_lab.items():
        names.setdefault(uf.find(k), lab)
    ports = []
    for sym, path, sd, a, pins in insts:
        if sd["type"] in LABEL_TYPES and pins:
            r = uf.find(pins[0][1])
            names[r] = a.get("lab", names.get(r, ""))
            if sd["type"] in ("ipin", "opin", "iopin"):
                ports.append(a.get("lab"))
            if sd.get("glob") and a.get("lab"):         # vdd.sym / gnd.sym: the net is global, in every sub-circuit too
                done.setdefault("__globals__", {})[a["lab"].lower()] = a["lab"]
    auto = [0]

    taken = {n.lower() for n in names.values()}

    def net(k):
        r = uf.find(k)
        if r not in names:
            auto[0] += 1
            while f"net{auto[0]}" in taken:
                auto[0] += 1
            names[r] = f"net{auto[0]}"
            taken.add(names[r])
        return names[r]

    lines, subckts = [], []
    for sym, path, sd, a, pins in insts:
        if sd["type"] in LABEL_TYPES:
            continue
        symname = os.path.splitext(os.path.basename(sym))[0]
        # instance arrays (x2[5:1]) become one instance per index; bus pins take one net per bit. A one-bit net
        # feeds every bit and every copy; a bus as wide as the pin feeds each copy; a wider one is split across copies
        inames = expand(a.get("name", ""))
        per_copy = [[] for _ in inames]
        pin_nets = [{} for _ in inames]          # pin name -> its net(s) per copy, for @@pin in a format
        for pname, k in pins:
            width = len(expand(pname))
            bits = expand(net(k))
            for ci in range(len(inames)):
                if len(bits) == width * len(inames) and len(inames) > 1:
                    chunk = bits[ci * width:(ci + 1) * width]
                elif len(bits) == width:
                    chunk = bits
                else:
                    chunk = (bits * width)[:width] if len(bits) == 1 else (bits + bits[-1:] * width)[:width]
                per_copy[ci] += chunk
                pin_nets[ci][pname] = " ".join(chunk)
        if len(inames) > 1:
            for ci, nm in enumerate(inames):
                a2 = dict(a, name=nm)
                _emit(lines, sd, a2, " ".join(per_copy[ci]), symname, pin_nets[ci])
            if sd["type"] == "subcircuit":
                sub = os.path.splitext(path)[0] + ".sch"
                if os.path.exists(sub) and symname not in done:
                    done[symname] = True
                    subckts += _subckt(sub, symname, sd, done)
            continue
        pinlist = " ".join(per_copy[0])
        if sd["type"] == "subcircuit":
            sub = os.path.splitext(path)[0] + ".sch"
            if os.path.exists(sub) and symname not in done:
                done[symname] = True
                subckts += build(sub, top=False, done=done) if False else _subckt(sub, symname, sd, done)
        _emit(lines, sd, a, pinlist, symname, pin_nets[0])
    lines += code
    if top:
        g = sorted((done.get("__globals__") or {}).values())
        return subckts + lines + [f".GLOBAL {n}" for n in g]           # one line per net, as xschem writes it
    return subckts, lines, ports


DEVICE_LINE = re.compile(r"^[xmrcdqlXMRCDQL][^\s=]*\s+\S")


def code_devices(value):
    """The device lines of a code block (code.sym / code_shown.sym) in a sub-cell: xschem copies a block that is not
    only_toplevel into the sub-circuit, and designers draw cells that way (a standard cell's transistors pasted as
    text). Element lines only (X M R C D Q L, '+' continuations joined); every dot-command, .control block and shell
    line stays out, as at the top level. In 98 cloned repos: 9 sub-cell blocks, 111 device lines (one design, 3 shuttles)."""
    out, ctl = [], False
    for raw in value.strip().strip('"').splitlines():
        l = raw.strip()
        if l.lower().startswith(".control"):
            ctl = True
        elif l.lower().startswith(".endc"):
            ctl = False
        elif ctl:
            continue
        elif l.startswith("+") and out:
            out[-1] += " " + l[1:].strip()
        elif DEVICE_LINE.match(l) and not re.search(r"[`$;|]", l):
            out.append(l)
    return out


def _emit(lines, sd, a, pinlist, symname, pin_nets=None):
    """One element line from the symbol's format, as xschem substitutes it. @@pin is the net on that pin (standard
    cell symbols list their signal pins this way); xschem's escaped `\\\\` joins two words (@prefix\\\\inv_1)."""
    pin_nets = pin_nets or {}
    def rep(m):
        k = m.group(1)
        if k == "pinlist":
            return pinlist
        if k == "symname":
            return symname
        if k == "name":
            return a.get("name", "")
        if k == "savecurrent":
            # xschem: savecurrent=true adds a .save of the element current; anything else adds nothing
            return f"\n.save i({a.get('name', '').lower()})" if a.get(k, "").lower() == "true" else ""
        v = a.get(k, a.get(k.lower(), ""))
        m2 = re.fullmatch(r"\s*expr\('(.*)'\)\s*", v)
        if m2:
            # xschem writes expr('...') defaults as the plain SPICE expression with @param -> param
            v = "'" + re.sub(r"\s+", "", re.sub(r"@(\w+)", r"\1", m2.group(1))).replace("*", " * ") + "'"
        return v
    line = re.sub(r"@@(\w+)", lambda m: pin_nets.get(m.group(1), m.group(0)), sd["format"])
    line = re.sub(r"@(\w+)", rep, line)
    line = re.sub(r"\\{2,}", "", line)
    # @@pin references (pin-specific nets) and stray tcl are not used by analog devices; strip them
    line = "\n".join(re.sub(r"[ \t]+", " ", x).strip() for x in line.replace("@", "").split("\n"))
    if line:
        lines.append(line)


def _subckt(sub_sch, symname, sd, done):
    """.subckt header as xschem writes it: the symbol's pins, then its extra= ports (supply pins passed as attributes),
    then as parameters the template defaults the format passes in as key=@key (not m, not the extra ports)."""
    subs, lines, _ = build(sub_sch, top=False, done=done)
    pins = [b for n, _, _ in sd["pins"] for b in expand(n)] + list(sd.get("extra") or [])
    passed = set(re.findall(r"(\w+)\s*=\s*@(\w+)", sd["format"]))
    params = [f"{k}={v}" for k, v in sd["template"].items()
              if (k, k) in passed and k not in ("m", "name") and k not in (sd.get("extra") or [])]
    return subs + [f".subckt {symname} {' '.join(pins + params)}"] + lines + [f".ends {symname}"]


def netlist(sch_path):
    return "\n".join(build(sch_path)) + "\n"


if __name__ == "__main__":
    sys.stdout.write(netlist(sys.argv[1]))

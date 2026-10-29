"""sch_svg.py — render an xschem schematic to SVG from its text (no xschem, nothing executed).

Geometry follows xschem's own conventions: instance placement `C {sym} x y rot flip {props}`, symbol primitives
L (line), B (box; layer 5 = pin), P (polygon), A (arc), T (text) and wires `N x1 y1 x2 y2 {lab=...}`, with xschem's
ROTATION transform (flip about the origin, then rot x 90 deg). Every wire and symbol stroke is drawn with
vector-effect: non-scaling-stroke so lines stay one crisp width at any zoom; text stays real SVG text. Each instance is
a <g data-dev="name"> and each wire a <path data-net="lab"> so the report can highlight a finding's device or net.
"""
import functools, html, math, os, re

from kaaval_engine.paths import SYMBOL_PATHS  # noqa: E402
PRIM = re.compile(r"^([LBPAT]) ", re.M)
KV = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\S+)')
TEXT_SCALE = 50.0          # xschem text size 1.0 ~ 50 drawing units tall
MIN_TEXT = {"name": 13.0, "lab": 13.0, "param": 11.0, "note": 11.0}   # drawing units; keeps labels readable


def _block(text, i):
    """text[i] is just after '{' -> (content, index after matching '}'), honouring \\ escapes."""
    depth, j = 1, i
    while j < len(text) and depth:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        depth += c == "{"
        depth -= c == "}"
        j += 1
    return text[i:j - 1], j


def _props(s):
    return {k: v.strip('"') for k, v in KV.findall(s)}


def parse(text):
    """Items of an xschem file: ('L'|'B'|'P'|'A'|'T'|'N'|'C', fields, props-text)."""
    items, i = [], 0
    for m in re.finditer(r"^([LBPATNC]) ", text, re.M):
        if m.start() < i:
            continue
        kind, j = m.group(1), m.end()
        if kind in "TC":
            if text[j] != "{":
                continue
            head, j = _block(text, j + 1)
        else:
            head = None
        k = text.find("{", j)
        nl = text.find("\n", j)
        if k < 0:
            continue
        fields = text[j:k].split()
        props, i = _block(text, k + 1)
        if head is not None:
            fields = [head] + fields
        items.append((kind, fields, props))
    return items


@functools.lru_cache(maxsize=None)
def load_symbol(sym, local_dir):
    for d in [local_dir] + SYMBOL_PATHS:
        p = os.path.join(d, sym)
        if os.path.exists(p):
            return parse(open(p, errors="replace").read())
    return None


def child_sheet(sch_path, inst):
    """The schematic behind instance `inst` (by its name= attribute) on sheet sch_path: the symbol's .sch, found
    beside the symbol the way xschem finds it. None when the instance is a primitive or its schematic is absent."""
    local = os.path.dirname(os.path.abspath(sch_path))
    for kind, f, props in parse(open(sch_path, errors="replace").read()):
        if kind != "C" or _props(props).get("name", "").lower() != inst.lower():
            continue
        for d in [local] + SYMBOL_PATHS:
            p = os.path.join(d, f[0])
            if os.path.exists(p):
                sch = os.path.splitext(p)[0] + ".sch"
                if os.path.exists(sch):
                    return sch
            # absolute paths from another machine: resolve by file name inside the repository folder
        base = os.path.splitext(os.path.basename(f[0]))[0] + ".sch"
        for dd, _, fs in os.walk(local):
            if base in fs:
                return os.path.join(dd, base)
    return None


def xform(x, y, rot, flip, ox=0.0, oy=0.0):
    xt = -x if flip else x
    if rot == 1:
        x2, y2 = -y, xt
    elif rot == 2:
        x2, y2 = -xt, -y
    elif rot == 3:
        x2, y2 = y, -xt
    else:
        x2, y2 = xt, y
    return x2 + ox, y2 + oy


def _sub(s, props, symname):
    """xschem @-substitution for display text."""
    def rep(m):
        k = m.group(1)
        if k == "symname":
            return symname
        return props.get(k, "")
    return re.sub(r"@(\w+)", rep, s)


def render(sch_path, highlight=(), width=None, annotate=None, callouts=None):
    """SVG string of the schematic.

    highlight: device names drawn in the 'hl' (finding) style; callouts: {device: badge text} placed above it;
    annotate: {net label: {state: text}} written on the net's longest wire, one <text class="op" data-state=...> per
    state, so the page can switch between e.g. "as written" and "fixed" operating points.
    """
    wires, labpos, last_text = {}, {}, [None]
    local = os.path.dirname(os.path.abspath(sch_path))
    items = parse(open(sch_path, errors="replace").read())
    out, xs, ys = [], [], []

    def pt(x, y):
        xs.append(x)
        ys.append(y)
        return f"{x:.2f} {y:.2f}"

    def text_el(s, x, y, size, rot, flip, cls):
        # keep text upright; alignment follows xschem: rot 0 -> start/top, rot 2 -> end/bottom, flip mirrors
        r = rot % 4
        fs = max(size * TEXT_SCALE, MIN_TEXT.get(cls, 6))
        if r in (1, 3):
            # vertical labels (pins on vertical wires) are set upright beside the point, never rotated over the wire
            anchor, base, tr = ("start" if not flip else "end"), "central", ""
            x = x + (fs * 0.5 if not flip else -fs * 0.5)
        else:
            anchor = "start" if (r == 0) != bool(flip) else "end"
            base, tr = ("hanging" if r == 0 else "text-after-edge"), ""
        wtxt = len(s) * fs * 0.62
        last_text[0] = (x, y, anchor, base, wtxt, fs)
        xs.extend([x, x + wtxt if anchor == "start" else x - wtxt])
        ys.extend([y, y + fs if base == "hanging" else y - fs])
        return (f'<text class="{cls}" x="{x:.2f}" y="{y:.2f}" font-size="{fs:.1f}" text-anchor="{anchor}" '
                f'dominant-baseline="{base}"{tr}>{html.escape(s)}</text>')

    for kind, f, props in items:
        if kind == "N":
            x1, y1, x2, y2 = map(float, f[:4])
            lab = _props(props).get("lab", "")
            wires.setdefault(lab, []).append((x1, y1, x2, y2))
            out.append(f'<path class="w" data-net="{html.escape(lab)}" d="M{pt(x1, y1)}L{pt(x2, y2)}"/>')
        elif kind == "T" and f:
            s = f[0]
            if any(k in s for k in ("tcleval", "spice_get", "\\")) or "@" in s:
                continue
            x, y, rot, flip, hs = float(f[1]), float(f[2]), int(f[3]), int(f[4]), float(f[5])
            out.append(text_el(s, x, y, hs, rot, flip, "note"))
        elif kind == "C":
            sym, x0, y0, rot, flip = f[0], float(f[1]), float(f[2]), int(f[3]), int(f[4])
            p = _props(props)
            prims = load_symbol(sym, local)
            name = p.get("name", "")
            symname = os.path.splitext(os.path.basename(sym))[0]
            if sym.endswith("title.sym") or "ngspice_" in sym or "probe" in sym or sym.endswith(("launcher.sym", "code.sym", "code_shown.sym")):
                continue
            cls = "dev hl" if name.lower() in {h.lower() for h in highlight} else "dev"
            n0 = len(xs)
            tip = " ".join(f"{k}={v}" for k, v in p.items() if k in ("model", "w", "l", "W", "L", "nf", "mult", "m", "area", "perim", "pj", "value") and v)
            g = [f'<g class="{cls}" data-dev="{html.escape(name)}" data-sym="{html.escape(symname)}"><title>{html.escape(name + " " + tip)}</title>']
            for k2, f2, pr2 in prims or []:
                q = _props(pr2)
                try:
                    if k2 == "L":
                        a = xform(float(f2[1]), float(f2[2]), rot, flip, x0, y0)
                        b = xform(float(f2[3]), float(f2[4]), rot, flip, x0, y0)
                        g.append(f'<path class="s" d="M{pt(*a)}L{pt(*b)}"/>')
                    elif k2 == "B":
                        a = xform(float(f2[1]), float(f2[2]), rot, flip, x0, y0)
                        b = xform(float(f2[3]), float(f2[4]), rot, flip, x0, y0)
                        if f2[0] == "5":     # pin square
                            g.append(f'<rect class="pin" x="{min(a[0], b[0]):.2f}" y="{min(a[1], b[1]):.2f}" '
                                     f'width="{abs(a[0] - b[0]):.2f}" height="{abs(a[1] - b[1]):.2f}"/>')
                            pt(*a); pt(*b)
                        else:
                            g.append(f'<path class="s" d="M{pt(a[0], a[1])}L{pt(b[0], a[1])}L{pt(b[0], b[1])}'
                                     f'L{pt(a[0], b[1])}Z"/>')
                    elif k2 == "P":
                        n = int(f2[1])
                        ps = [xform(float(f2[2 + 2 * i]), float(f2[3 + 2 * i]), rot, flip, x0, y0) for i in range(n)]
                        fill = "fill" if q.get("fill") == "true" else "s"
                        g.append(f'<path class="{fill}" d="M' + "L".join(pt(*c) for c in ps) + '"/>')
                    elif k2 == "A":
                        cx, cy, r, a0, sweep = map(float, f2[1:6])
                        pts = []
                        steps = max(8, int(abs(sweep) / 10))
                        for i in range(steps + 1):
                            ang = math.radians(a0 + sweep * i / steps)
                            pts.append(xform(cx + r * math.cos(ang), cy - r * math.sin(ang), rot, flip, x0, y0))
                        g.append('<path class="s" d="M' + "L".join(pt(*c) for c in pts) + '"/>')
                    elif k2 == "T" and f2:
                        if f2[0] not in ("@name", "@lab") or q.get("layer") == "7":
                            continue
                        s = _sub(f2[0], p, symname)
                        if not s.strip() or not sym.startswith(("sky130_fd_pr/", "devices/lab", "devices/ipin",
                                                                "devices/opin", "devices/iopin")) and f2[0] == "@name":
                            continue
                        tx, ty = xform(float(f2[1]), float(f2[2]), rot, flip, x0, y0)
                        tr = (int(f2[3]) + rot) % 4
                        tf = int(f2[4]) ^ flip
                        role = "name" if f2[0] == "@name" else ("lab" if "@lab" in f2[0] else "param")
                        g.append(text_el(s, tx, ty, float(f2[5]), tr, tf, role))
                        if role == "lab":
                            labpos.setdefault(s, []).append(last_text[0])
                except (ValueError, IndexError):
                    continue
            g.append("</g>")
            if name in (callouts or {}) and len(xs) > n0:
                bx0, bx1, by0 = min(xs[n0:]), max(xs[n0:]), min(ys[n0:])
                cx = (bx0 + bx1) / 2
                t = callouts[name]
                bw = len(t) * 9 + 18
                g.append(f'<g class="callout" data-dev="{html.escape(name)}"><rect x="{cx - bw / 2:.1f}" y="{by0 - 30:.1f}" '
                         f'width="{bw:.1f}" height="22" rx="11"/><text x="{cx:.1f}" y="{by0 - 19:.1f}" '
                         f'text-anchor="middle" dominant-baseline="central">{html.escape(t)}</text></g>')
                pt(cx - bw / 2, by0 - 32)
            out += g
    for net, states in (annotate or {}).items():
        segs = wires.get(net) or []
        if not segs and net not in labpos:
            continue
        verts = [w for w in segs if abs(w[0] - w[2]) < 1e-6 and abs(w[3] - w[1]) >= 30]
        if verts:
            # beside the net's longest vertical run: the free space next to a node's drop wire, away from the
            # labels that crowd horizontal runs
            a = max(verts, key=lambda w: abs(w[3] - w[1]))
            tx, ty, anchor, base = a[0] + 8, (a[1] + a[3]) / 2, "start", "central"
        elif segs:
            a = max(segs, key=lambda w: abs(w[2] - w[0]))
            tx, ty, anchor, base = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2 - 8, "middle", "text-after-edge"
        else:
            lx, ly, la, lb, lw, lfs = labpos[net][0]
            tx, ty, anchor, base = (lx + lw + 8 if la == "start" else lx + 8), ly, "start", lb
        for st, txt in states.items():
            out.append(f'<text class="op" data-state="{html.escape(st)}" data-net="{html.escape(net)}" x="{tx:.1f}" '
                       f'y="{ty:.1f}" text-anchor="{anchor}" dominant-baseline="{base}">{html.escape(txt)}</text>')
        pt(tx - 30, ty)
        pt(tx + 40, ty + 14)
    pad = 30
    x0, y0, x1, y1 = min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    w = f' width="{width}"' if width else ""
    return (f'<svg class="sch" xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {x1 - x0:.0f} '
            f'{y1 - y0:.0f}"{w} role="img" aria-label="schematic {html.escape(os.path.basename(sch_path))}">'
            + "".join(out) + "</svg>")


if __name__ == "__main__":
    import sys
    print(render(sys.argv[1], highlight=tuple(sys.argv[2:])))

"""layout3d.py — a cell's committed Magic layout as stacked 3D layers: every rectangle of every layer, sub-cells placed
by their own transforms, each layer at its sky130 height, for the bench's 3D view.

Read as text (.mag files: `<< layer >>` sections of `rect x1 y1 x2 y2`, `use` / `transform` / `box` / `array` for
sub-cells); sub-cells are found in the repository first, then in the PDK's Magic libraries. Nothing is executed. The
heights are sky130's nominal stack (µm above the substrate, from the PDK documentation) and only order the layers:
the view shows what is drawn, not a process simulation. Triangles (`tri`) are drawn as their bounding boxes.
"""
import os, re

from kaaval_engine.layout_check import PDK_ROOT

# Magic sky130 layer names -> (group, z bottom µm, thickness µm). Wells, diffusion and implants sit at the surface;
# contacts and vias span the gap between the layers they join.
STACK = [
    (r"^(nwell|pwell|dnwell)$", "well", 0.0, 0.05),
    (r"^(n|p|mv|hv)?(diff|ndiff|pdiff|nsubdiff|psubdiff|mvndiff|mvpdiff|mvnsubdiff|mvpsubdiff|.*diff|.*diode)$", "diffusion", 0.05, 0.12),
    (r"^(n|p|mvn|mvp|sc|scn|scp)?mos.*|.*fet.*$", "gate", 0.12, 0.2),
    (r"^(poly|xpolycontact|xhrpoly|uhrpoly|rpoly|ppolyres|npolyres|xpolyres|.*polyres)$", "poly", 0.17, 0.18),
    (r"^(ndiffc|pdiffc|nsubdiffcont|psubdiffcont|.*diffc|.*diodec|.*cont|polycont|ndc|pdc|nsc|psc|pc)$", "contact", 0.17, 0.77),
    (r"^(locali|li|li1|rlocali)$", "li", 0.94, 0.1),
    (r"^(viali|mcon|licon)$", "mcon", 1.04, 0.34),
    (r"^(metal1|m1)$", "metal1", 1.38, 0.36),
    (r"^(via1|via|m2contact|v1)$", "via1", 1.74, 0.27),
    (r"^(metal2|m2)$", "metal2", 2.01, 0.36),
    (r"^(via2|m3contact|v2)$", "via2", 2.37, 0.42),
    (r"^(metal3|m3)$", "metal3", 2.79, 0.85),
    (r"^(via3|m4contact|v3|mimcapcontact)$", "via3", 3.64, 0.39),
    (r"^(metal4|m4|mimcap|mimcc)$", "metal4", 4.02, 0.85),
    (r"^(via4|m5contact|v4|mimcap2contact)$", "via4", 4.87, 0.5),
    (r"^(metal5|m5|mimcap2|mimcc2)$", "metal5", 5.37, 1.26),
]
SKIP = {"labels", "properties", "end", "error_p", "error_s", "error_ps", "checkpaint", "comment", "boundary",
        "fixed_bbox", "glass", "pnp", "npn", "obsli", "obsm1", "obsm2", "obsm3", "obsm4", "obsm5"}
MAX_RECTS = 120_000


def group(layer):
    for pat, g, z, h in STACK:
        if re.match(pat, layer):
            return g, z, h
    return None


def _index(root):
    """{cell name: .mag path} in the repository, then the PDK's Magic libraries (sky130_fd_pr devices, standard cells)."""
    idx = {}
    dirs = [root] + [os.path.join(PDK_ROOT, "libs.ref", lib, "mag") for lib in
                     ("sky130_fd_pr", "sky130_fd_sc_hd", "sky130_fd_sc_hvl", "sky130_fd_io")]
    for base in dirs:
        if not os.path.isdir(base):
            continue
        for d, ds, fs in os.walk(base):
            ds[:] = [x for x in ds if not x.startswith(".")]
            for f in fs:
                if f.endswith(".mag"):
                    idx.setdefault(f[:-4], os.path.join(d, f))
    return idx


def _parse(path):
    """(rects {layer: [(x1, y1, x2, y2)]}, uses [(cell, transform (a b c d e f), array or None)], scale)."""
    rects, uses, layer, cur, scale = {}, [], None, None, 1.0
    for line in open(path, errors="replace"):
        t = line.split()
        if not t:
            continue
        if t[0] == "magscale" and len(t) == 3:
            scale = float(t[1]) / float(t[2])
        elif t[0] == "<<":
            layer = t[1] if len(t) > 1 else None
            cur = None
        elif t[0] in ("rect", "tri") and layer and layer not in SKIP and len(t) >= 5:
            try:
                rects.setdefault(layer, []).append(tuple(int(v) for v in t[1:5]))
            except ValueError:
                pass
        elif t[0] == "use" and len(t) >= 2:
            cur = [t[1], (1, 0, 0, 0, 1, 0), None]
            uses.append(cur)
        elif t[0] == "transform" and cur and len(t) == 7:
            cur[1] = tuple(int(v) for v in t[1:7])
        elif t[0] == "array" and cur and len(t) == 7:
            cur[2] = tuple(int(v) for v in t[1:7])
    return rects, uses, scale


def _compose(outer, inner):
    a, b, c, d, e, f = outer
    A, B, C, D, E, F = inner
    return (a * A + b * D, a * B + b * E, a * C + b * F + c, d * A + e * D, d * B + e * E, d * C + e * F + f)


def _apply(T, r):
    a, b, c, d, e, f = T
    xs = [a * x + b * y + c for x, y in ((r[0], r[1]), (r[2], r[3]))]
    ys = [d * x + e * y + f for x, y in ((r[0], r[1]), (r[2], r[3]))]
    return (min(xs), min(ys), max(xs), max(ys))


def read(root, mag):
    """The layout of `mag` (a .mag path relative to root, inside it) flattened: {cell, unit_um, bbox, layers: [{name,
    group, z, h, rects}], cells, truncated}. Coordinates are Magic internal units; unit_um converts them to µm."""
    top = os.path.realpath(os.path.join(root, mag))
    if not top.startswith(os.path.realpath(root) + os.sep) or not top.endswith(".mag") or not os.path.isfile(top):
        raise ValueError("no such layout in the repository")
    idx, cache, out, seen = _index(root), {}, {}, set()
    total = [0]
    _, _, scale = _parse(top)

    def walk(path, T, depth):
        if depth > 16 or total[0] >= MAX_RECTS:
            return
        if path not in cache:
            cache[path] = _parse(path)
        rects, uses, _ = cache[path]
        seen.add(os.path.basename(path)[:-4])
        for layer, rs in rects.items():
            dst = out.setdefault(layer, [])
            for r in rs:
                if total[0] >= MAX_RECTS:
                    return
                dst.append(_apply(T, r))
                total[0] += 1
        for cell, tr, arr in uses:
            sub = idx.get(cell)
            if not sub:
                continue
            steps = [(0, 0)]
            if arr:                                    # array xlo xhi xsep ylo yhi ysep
                xlo, xhi, xs, ylo, yhi, ys = arr
                steps = [(i * xs, j * ys) for i in range(xhi - xlo + 1) for j in range(yhi - ylo + 1)][:256]
            for dx, dy in steps:
                walk(sub, _compose(T, _compose(tr, (1, 0, dx, 0, 1, dy))), depth + 1)

    walk(top, (1, 0, 0, 0, 1, 0), 0)
    layers = []
    for name, rs in out.items():
        g = group(name)
        if g and rs:
            layers.append(dict(name=name, group=g[0], z=g[1], h=g[2], rects=rs))
    layers.sort(key=lambda l: (l["z"], l["name"]))
    pts = [r for l in layers for r in l["rects"]]
    bbox = [min(r[0] for r in pts), min(r[1] for r in pts), max(r[2] for r in pts), max(r[3] for r in pts)] if pts else None
    return dict(cell=os.path.basename(mag)[:-4], unit_um=0.01 * scale, bbox=bbox, layers=layers, cells=sorted(seen),
                truncated=total[0] >= MAX_RECTS)

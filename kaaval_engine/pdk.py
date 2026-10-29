"""pdk.py — a per-design trimmed sky130 library: the full corner structure, only the device models the design uses.

Loading the full sky130 library is most of an ngspice run (~9 s). Its corner sections include one model file per
device family (nfet_01v8, pfet_01v8_lvt, g5v0d10v5, diodes, bipolars, special cells ...); a design uses a handful.
The trimmed library keeps every parameter / resistor / capacitor / corner file and drops only model-file includes
whose device family the netlist never instantiates. Results must be identical to the full library (checked in
tests), it is only faster. Cached per (device set, corner) under ~/.kaaval/pdk.
"""
import hashlib, os, re

from kaaval_engine.paths import PDK_LIB as FULL
CACHE = os.path.expanduser(os.environ.get("KAAVAL_PDK_CACHE", "~/.kaaval/pdk"))
INC = re.compile(r'^\s*\.include\s+"?([^"\s]+)"?', re.I)
FAMILY = re.compile(r"sky130_fd_pr__([a-z0-9_]+?)(?:__|\.)")


def used_models(circuit):
    return {m for m in re.findall(r"\bsky130_fd_pr__([a-z0-9_]+)", circuit.lower())}


def _keep(path, used):
    """Keep a model-file include only if its device family is used; keep everything that is not a model file."""
    base = os.path.basename(path).lower()
    m = FAMILY.search(base)
    if not m or "model__" in base:          # infrastructure (lod, r+c, nonfet, head, model__ files): keep
        return True
    fam = m.group(1)
    return any(fam == u or fam.startswith(u + "_") and False or u == fam for u in used) or \
        any(base.startswith(f"sky130_fd_pr__{u}__") or base.startswith(f"sky130_fd_pr__{u}.") for u in used)


def _expand(path, used, out, depth=0):
    d = os.path.dirname(path)
    for line in open(path, errors="replace"):
        m = INC.match(line)
        if not m:
            out.append(line.rstrip("\n"))
            continue
        target = os.path.normpath(os.path.join(d, m.group(1)))
        name = os.path.basename(target)
        # descend into the files that hold include lists (corner files and all.spice); keep or drop leaf models
        if depth < 3 and (name in ("all.spice",) or os.path.dirname(target).endswith("corners")):
            out.append(f"* --- {name} (trimmed)")
            _expand(target, used, out, depth + 1)
        elif _keep(target, used):
            out.append(f'.include "{target}"')


REF = re.compile(r"\bsky130_fd_pr__([a-z0-9_]+?)__[a-z0-9_]+", re.I)


def _closure(sec_lines, used):
    """Families whose parameters the kept model files refer to (the PNP models read the pfet junction multipliers,
    for example): without them ngspice stops on an undefined parameter."""
    more = set()
    for line in sec_lines:
        m = INC.match(line)
        if m and os.path.isfile(m.group(1)) and FAMILY.search(os.path.basename(m.group(1)).lower()):
            more.update(f.lower() for f in REF.findall(open(m.group(1), errors="replace").read()))
    return used | more


def lib_for(circuit, corner):
    """Path of a trimmed library whose `.lib <corner>` section loads only what `circuit` needs, plus every model family
    those models depend on."""
    used = used_models(circuit)
    for _ in range(4):
        grown = _closure(_section(corner, used) or [], used)
        if grown == used:
            break
        used = grown
    key = hashlib.sha1(("v2|" + ",".join(sorted(used)) + "|" + corner + "|" + str(os.path.getmtime(FULL))).encode()).hexdigest()[:16]
    os.makedirs(CACHE, exist_ok=True)
    out_path = os.path.join(CACHE, f"sky130_{corner}_{key}.lib.spice")
    if os.path.exists(out_path):
        return out_path
    sec_lines = _section(corner, used)
    if sec_lines is None:
        return FULL
    out = [f"* Kaaval trimmed sky130 library: corner {corner}; models for {', '.join(sorted(used))}", f".lib {corner}"]
    out += sec_lines + [f".endl {corner}"]
    open(out_path, "w").write("\n".join(out) + "\n")
    return out_path


def _section(corner, used):
    text = open(FULL, errors="replace").read()
    m = re.search(rf"^\.lib\s+{re.escape(corner)}\s*$(.*?)^\.endl\s+{re.escape(corner)}\s*$", text, re.M | re.S)
    if not m:
        return None
    # the section's relative includes are relative to the full library's folder
    sec_lines = []
    for line in m.group(1).splitlines():
        mm = INC.match(line)
        if mm:
            target = os.path.normpath(os.path.join(os.path.dirname(FULL), mm.group(1)))
            if os.path.dirname(target).endswith("corners") and target.endswith(".spice") and "/" not in mm.group(1).split("corners/")[-1]:
                sec_lines.append(f"* --- {os.path.basename(target)} (trimmed)")
                _expand(target, used, sec_lines, 1)
            elif _keep(target, used):
                sec_lines.append(f'.include "{target}"')
        else:
            sec_lines.append(line)
    return sec_lines

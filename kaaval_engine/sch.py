"""sch.py — read xschem schematics as TEXT and turn sky130 device instances into SPICE-like lines.

Nothing in the schematic is executed (xschem files can carry Tcl; a third-party repo is untrusted). Each instance's
own attributes are merged over the defaults of the PDK's trusted symbol (template= in libs.tech/xschem/<sym>), and
the symbol's format= string decides which parameters reach the netlist (e.g. area/perim vs area/pj), the same way
xschem itself would build the line.
"""
import functools, os, re

from kaaval_engine.paths import PDK_XSCHEM
INST = re.compile(r"^C \{([^}]*)\}\s+\S+\s+\S+\s+\S+\s+\S+\s+\{", re.M)
KV = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\S+)')


def _block(text, start):
    """text[start] is just after an opening '{'; return (content, end) up to the matching '}' (\\{ escaped)."""
    depth, i = 1, start
    while i < len(text) and depth:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        depth += c == "{"
        depth -= c == "}"
        i += 1
    return text[start:i - 1], i


def attrs(s):
    return {k.lower(): v.strip('"') for k, v in KV.findall(s)}


@functools.lru_cache(maxsize=None)
def symbol(sym):
    """(defaults, format params) of a PDK symbol, or None when it is not a trusted PDK device symbol."""
    path = os.path.join(PDK_XSCHEM, sym)
    if not sym.startswith("sky130_fd_pr/") or not os.path.exists(path):
        return None
    text = open(path, errors="replace").read()
    k = re.search(r"^K \{", text, re.M)
    if not k:
        return None
    body, _ = _block(text, k.end())
    fmt = re.search(r'format="([^"]*)"', body)
    tpl = re.search(r'template="([^"]*)"', body, re.S)
    params = re.findall(r"(\w+)=@(\w+)", fmt.group(1)) if fmt else []
    return attrs(tpl.group(1) if tpl else ""), params


def device_lines(path):
    """(line_no, 'X<name> sky130_fd_pr__<model> k=v ...') for every PDK device instance in an xschem schematic."""
    text = open(path, errors="replace").read()
    out = []
    for m in INST.finditer(text):
        sym = m.group(1).strip()
        sd = symbol(sym)
        if not sd:
            continue
        defaults, params = sd
        body, _ = _block(text, m.end())
        a = dict(defaults, **attrs(body))
        model = a.get("model", "")
        if not model:
            continue
        model = model if model.startswith("sky130_fd_pr__") else "sky130_fd_pr__" + model
        kv = " ".join(f"{k}={a.get(v.lower(), '')}" for k, v in params if a.get(v.lower(), "") != "")
        out.append((text.count("\n", 0, m.start()) + 1, f"X{a.get('name', '?')} {model} {kv}"))
    return out

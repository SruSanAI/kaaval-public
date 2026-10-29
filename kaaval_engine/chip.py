"""chip.py — the whole Tiny Tapeout tile of a project, read as text: rails, pads, the macros and how they connect.

A Tiny Tapeout project is one tile: a top module with fixed pins (VDPWR 1.8 V, VAPWR 3.3 V, VGND, ui_in, uo_out,
uio_*, ua analog pads, clk, rst_n, ena) wrapping the designer's blocks. info.yaml says which analog pads are paid for and
whether 3.3 V is used; src/*.v instantiates the blocks. This module reads both (never runs them) and returns the tile as
a graph: every instance, every one of its pins, and what that pin reaches - a rail, an analog pad, a digital input or
output pad, the clock or reset, another instance, or nothing. Instances whose type is a cell in the repository
(a schematic or SPICE subcircuit of that name) are marked analog, so a viewer can open them.

    tile = read(root)        # {top, uses_3v3, analog_pins, rails, pads, instances: [{type, name, cell, pins}], notes}
"""
import os
import re

RAILS = {"vpwr": ("VDPWR", 1.8), "vdpwr": ("VDPWR", 1.8), "vapwr": ("VAPWR", 3.3), "vgnd": ("VGND", 0.0), "vccd1": ("VDPWR", 1.8),
         "vssd1": ("VGND", 0.0), "vdda1": ("VAPWR", 3.3), "vssa1": ("VGND", 0.0)}
BUSES = ("ui_in", "uo_out", "uio_in", "uio_out", "uio_oe", "ua")
EXTRACTED = re.compile(r"(?i)\.(lvs|pex|sim|rc)\.|parax|_pex|pex")
KEYWORDS = {"module", "input", "output", "inout", "wire", "reg", "assign", "always", "if", "else", "begin", "end",
            "endmodule", "localparam", "parameter", "generate", "endgenerate", "for", "case", "endcase", "initial"}


def _yaml(text):
    get = lambda k: (re.search(rf"^\s*{k}\s*:\s*\"?([^\"#\n]*)", text, re.M) or [None, ""])[1].strip()
    pins = {m.group(1): m.group(2) for m in re.finditer(r"^\s*((?:ua|ui|uo|uio)\[\d\])\s*:\s*\"([^\"]*)\"", text, re.M)}
    ap = get("analog_pins")
    return dict(top=get("top_module"), uses_3v3=get("uses_3v3").lower() == "true",
                analog_pins=int(ap) if ap.isdigit() else None, pinout=pins)


def _strip(v):
    v = re.sub(r"/\*.*?\*/", " ", v, flags=re.S)
    return re.sub(r"//[^\n]*", "", v)


def _instances(v):
    """[(type, name, {port: net expression})] for named-port instances in Verilog text."""
    out = []
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s+(?:#\s*\((?:[^()]|\([^()]*\))*\)\s*)?([A-Za-z_]\w*)\s*\(\s*\.", v):
        typ, name = m.group(1), m.group(2)
        if typ in KEYWORDS or name in KEYWORDS:
            continue
        start = v.index("(", m.end(2))                 # the port list's opening parenthesis
        depth, i = 0, start
        while i < len(v):                              # ...and its closing one
            depth += {"(": 1, ")": -1}.get(v[i], 0)
            i += 1
            if depth == 0:
                break
        body = v[start + 1:i - 1]
        conns = {p: n.strip() for p, n in re.findall(r"\.(\w+)\s*\(\s*([^()]*?(?:\([^()]*\))?[^()]*?)\s*\)", body)}
        out.append((typ, name, conns))
    return out


def _cells(root):
    """{name lower: relative path} of schematic and SPICE subcircuit cells in the repository."""
    out, sch = {}, set()
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in sorted(fs, key=lambda f: not f.endswith(".sch")):
            p = os.path.join(d, f)
            if f.endswith(".sch"):                     # a schematic beats any netlist of the same cell
                out[os.path.splitext(f)[0].lower()] = os.path.relpath(p, root)
                sch.add(os.path.splitext(f)[0].lower())
            elif f.lower().endswith((".spice", ".sp", ".cir", ".spi")):
                try:
                    for n in re.findall(r"(?im)^\s*\.subckt\s+(\S+)", open(p, errors="replace").read(1_000_000)):
                        if n.lower() not in sch:
                            # a plain netlist beats a layout-extracted one (.lvs / .pex / parasitic copies)
                            old = out.get(n.lower())
                            if not old or (EXTRACTED.search(old) and not EXTRACTED.search(f)):
                                out[n.lower()] = os.path.relpath(p, root) + "#" + n
                except OSError:
                    pass
    return out


def classify(net, inst_nets):
    """What a net expression reaches at the tile's edge."""
    n = net.strip()
    low = n.lower()
    if not n:
        return dict(kind="none")
    if low in RAILS:
        name, v = RAILS[low]
        return dict(kind="rail", rail=name, volts=v)
    m = re.match(r"(ua|ui_in|uo_out|uio_in|uio_out|uio_oe)\s*\[\s*(\d+)\s*\]$", low)
    if m:
        bus, i = m.group(1), int(m.group(2))
        kind = {"ua": "analog_pad", "ui_in": "digital_in", "uio_in": "digital_in"}.get(bus, "digital_out")
        return dict(kind=kind, pad=f"{bus}[{i}]")
    if low in ("clk", "rst_n", "ena"):
        return dict(kind={"clk": "clock", "rst_n": "reset", "ena": "enable"}[low], pad=low)
    if re.match(r"^\d+'[bdh][0-9a-fx_]+$|^[01]$", low):
        return dict(kind="constant", value=n)
    if inst_nets.get(low, 0) > 1:
        return dict(kind="internal")
    return dict(kind="other")


def read(root):
    info = {}
    if os.path.isfile(os.path.join(root, "info.yaml")):
        info = _yaml(open(os.path.join(root, "info.yaml"), errors="replace").read())
    src = ""
    for d, dirs, fs in os.walk(os.path.join(root, "src")):
        for f in sorted(fs):
            if f.endswith((".v", ".sv")):
                src += "\n" + _strip(open(os.path.join(d, f), errors="replace").read(2_000_000))
    top = info.get("top") or ""
    mods = {m.group(1): m.group(2) for m in re.finditer(r"\bmodule\s+(\w+)\b(.*?)\bendmodule\b", src, re.S)}
    # the tile is the top module's own instances (a synthesized gate netlist elsewhere in src/ is not the design)
    insts = _instances(mods.get(top, src))
    count = {}
    for _, _, conns in insts:
        for net in conns.values():
            count[net.lower()] = count.get(net.lower(), 0) + 1
    cells = _cells(root)
    out = []
    for typ, name, conns in insts:
        cell = cells.get(typ.lower())
        out.append(dict(type=typ, name=name, cell=cell, analog=bool(cell), digital=typ in mods and not cell,
                        pins=[dict(port=p, net=n, **classify(n, count)) for p, n in conns.items()]))
    used_ua = sorted({p["pad"] for i in out for p in i["pins"] if p["kind"] == "analog_pad"},
                     key=lambda s: int(s[3:-1]))
    rails = sorted({p["rail"] for i in out for p in i["pins"] if p["kind"] == "rail"})
    return dict(top=top, uses_3v3=info.get("uses_3v3"), analog_pins=info.get("analog_pins"),
                pinout=info.get("pinout", {}), rails=rails, analog_pads=used_ua, instances=out)

"""spice_cells.py — circuit cells from SPICE netlist files, for repositories that have no xschem schematics.

Some open-silicon repositories carry their analog circuits only as SPICE text (.spice/.sp/.cir/.spi). Every
`.subckt NAME ports...` block in such a file is a cell, named "<file>#<NAME>", with its ports from the .subckt line.
Only the subcircuit definitions are kept: element lines, continuations and .param lines inside .subckt blocks.
Everything else - .include, .lib, .option, .control blocks, analyses, shell commands - is dropped, so nothing written
in the repository is ever executed; the engine adds its own PDK, sources and analyses around the cell.
"""
import os
import re

EXT = (".spice", ".sp", ".cir", ".spi", ".net")
KEEP_DOT = re.compile(r"^\s*\.(subckt|ends|param)\b", re.I)


def _subckts(text):
    """{name_lower: (name, ports, lines)} of every .subckt block, sanitised."""
    out, cur, lines, in_ctl = {}, None, [], False
    for raw in text.splitlines():
        s = raw.strip()
        low = s.lower()
        if low.startswith(".control"):
            in_ctl = True
            continue
        if low.startswith(".endc"):
            in_ctl = False
            continue
        if in_ctl or not s or s.startswith("*"):
            continue
        if low.startswith(".subckt"):
            p = re.sub(r"\s+(params:|\w+=).*$", "", s, flags=re.I).split()
            cur, lines = (p[1], [x for x in p[2:]]), [s]
            continue
        if cur is None:
            continue
        if low.startswith(".ends"):
            lines.append(s)
            out[cur[0].lower()] = (cur[0], cur[1], lines)
            cur = None
            continue
        if s.startswith(".") and not KEEP_DOT.match(s):
            continue                        # .include / .lib / .option / analyses inside a block: dropped
        lines.append(s)
    return out


def find_cells(root, limit=60):
    """Cells from SPICE files under root: [{cell, ports, devices, netlist}], largest first."""
    found = []
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in fs:
            if not f.lower().endswith(EXT):
                continue
            p = os.path.join(d, f)
            try:
                text = open(p, errors="replace").read(2_000_000)
            except OSError:
                continue
            subs = _subckts(text)
            for name, ports, lines in subs.values():
                devs = sum(1 for l in lines if l[:1].lower() in "xmqrcdl" and not l.startswith("."))
                if devs and ports:
                    found.append(dict(cell=f"{os.path.relpath(p, root)}#{name}", ports=ports, devices=devs,
                                      netlist="\n".join(lines)[:12000]))
    found.sort(key=lambda c: -c["devices"])
    return found[:limit]


def load(root, ident):
    """(circuit, ports) for cell "<file>#<NAME>": every sanitised .subckt of that file (a cell may use its siblings)
    plus one top-level instance whose nets are the port names, so plans address ports exactly as listed."""
    rel, _, name = ident.partition("#")
    p = os.path.realpath(os.path.join(root, rel))
    if not name or not p.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(p):
        return None, None
    subs = _subckts(open(p, errors="replace").read(2_000_000))
    if name.lower() not in subs:
        return None, None
    nm, ports, _ = subs[name.lower()]
    body = "\n".join("\n".join(lines) for _, _, lines in subs.values())
    return body + f"\nXdut {' '.join(ports)} {nm}", ports

"""stdcells.py — sky130 standard-cell subcircuits for designs that instantiate them.

Mixed-signal cells often use digital standard cells (sky130_fd_sc_hd__inv_1, ..._hvl__ for 3.3 V) next to
transistors. Their transistor-level definitions ship with the PDK (libs.ref/<lib>/spice/<lib>.spice); only the cells a
circuit instantiates and does not define itself are added, so the deck stays small and the model trim (pdk.lib_for)
sees the transistor families they use.
"""
import functools, os, re

from kaaval_engine.paths import PDK_ROOT

LIBS = ("sky130_fd_sc_hd", "sky130_fd_sc_hvl")
CELL = re.compile(r"\b(sky130_fd_sc_(?:hd|hvl)__\w+)", re.I)


@functools.lru_cache(maxsize=None)
def _library(lib):
    """{cell name (lower): definition text} of one standard-cell library."""
    p = os.path.join(PDK_ROOT, "libs.ref", lib, "spice", f"{lib}.spice")
    out, cur, lines = {}, None, []
    if not os.path.isfile(p):
        return out
    for line in open(p, errors="replace"):
        low = line.strip().lower()
        if low.startswith(".subckt"):
            cur, lines = low.split()[1], [line.rstrip()]
        elif cur:
            lines.append(line.rstrip())
            if low.startswith(".ends"):
                out[cur] = "\n".join(lines)
                cur = None
    return out


def defs_for(circuit):
    """Definitions of every standard cell `circuit` instantiates but does not define (and of the cells those use)."""
    defined = {l.split()[1].lower() for l in circuit.splitlines() if l.strip().lower().startswith(".subckt")
               and len(l.split()) > 1}
    want, out, seen = [], [], set()
    for l in circuit.splitlines():
        if l[:1].lower() == "x":
            want += [m.lower() for m in CELL.findall(l)]
    while want:
        c = want.pop()
        if c in seen or c in defined:
            continue
        seen.add(c)
        lib = "sky130_fd_sc_hvl" if "_hvl__" in c else "sky130_fd_sc_hd"
        d = _library(lib).get(c)
        if d:
            out.append(d)
            want += [m.lower() for m in CELL.findall("\n".join(d.splitlines()[1:]))]
    return "\n".join(out)

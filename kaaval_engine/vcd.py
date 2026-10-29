"""vcd.py — a control pin's real timing from a digital simulation (Value Change Dump), for the sequence test.

On a mixed-signal chip the enables and resets of an analog block come from the project's own logic, not from the
rails. A digital simulation (iverilog, Verilator, cocotb: any of them writes VCD) records when each of those signals
changes; this module reads that text and turns one signal into the breakpoints the engine drives the analog control
pin with. Only the VCD text is read; nothing is executed.

    sig = vcd.parse(open("tb.vcd").read())          # {"tb.dut.en": [(t_seconds, "0"|"1"|"x"|"z"|"b0101"), ...]}
    w = vcd.wave(sig["tb.dut.en"])                  # [[t, 0|1], ...]: a plan's control "wave"
"""
import re

MAX_EDGES = 200                    # a control changes a few times; a clock is not a control
UNITS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}


def parse(text):
    """{full signal name: [(t seconds, value)]} for every variable in the dump, in time order. A vector's value is
    "b<bits>"; one-bit values are "0", "1", "x" or "z"."""
    m = re.search(r"\$timescale\s+(\d+)\s*([munpf]?s)\s+\$end", text)
    unit = int(m.group(1)) * UNITS[m.group(2)] if m else 1e-9
    ids, scope, out = {}, [], {}
    head, _, body = text.partition("$enddefinitions")
    for tok in re.finditer(r"\$(scope|upscope|var)\b(.*?)\$end", head, re.S):
        kind, rest = tok.group(1), tok.group(2).split()
        if kind == "scope":
            scope.append(rest[1])
        elif kind == "upscope":
            scope.pop()
        else:                      # $var <type> <width> <id> <name> [range]
            name = ".".join(scope + [rest[3]])
            ids.setdefault(rest[2], []).append(name)
            out[name] = []
    t = 0.0
    words = iter(body.split())
    for w in words:
        if w[0] == "#":
            t = int(w[1:]) * unit
        elif w[0] in "01xzXZ" and w[1:] in ids:
            for n in ids[w[1:]]:
                out[n].append((t, w[0].lower()))
        elif w[0] in "bBrR":                    # "b0101 <id>" (vector) or "r1.5 <id>" (real): value, then id
            ident = next(words, None)
            for n in ids.get(ident, []):
                out[n].append((t, "b" + w[1:].lower()))
    return out


def find(signals, name):
    """The one signal whose full name ends with `name` (".en" or "dut.en"); None if none or several match."""
    hits = [n for n in signals if n == name or n.endswith("." + name)]
    return hits[0] if len(hits) == 1 else None


def wave(changes, invert=False):
    """[[t, 0|1]] breakpoints of a one-bit signal: one entry per change of its logic level, x and z read as 0 (a pin
    not yet driven). Raises ValueError for a vector or for more than MAX_EDGES changes (a clock, not a control)."""
    pts, last = [], None
    for t, v in changes:
        if v.startswith("b"):
            raise ValueError("a vector, not a one-bit control")
        b = 1 if v == "1" else 0
        b = 1 - b if invert else b
        if b != last:
            pts.append([t, b])
            last = b
    if len(pts) > MAX_EDGES:
        raise ValueError(f"{len(pts)} changes: a clock or data line, not an enable or reset")
    return pts

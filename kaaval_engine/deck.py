"""deck.py — rebuild a clean, inert circuit deck from a third-party SPICE file, for our own testbench.

Only circuit elements and .subckt / .ends / .param / .global survive. Every control or file directive (.control
blocks, .include / .lib, .option, analyses, .save, .write, shell commands) is dropped, so simulating the result runs
none of the repo's code; the caller adds the PDK library, the options and the analysis it wants.
"""
import re

ELEMENT = re.compile(r"^[rclvixmdqefghbkj]", re.I)
KEEP_DOT = (".subckt", ".ends", ".param", ".global")


def clean(text, rename=None):
    """Circuit-only lines of a SPICE deck; rename maps an element's parameter text (old -> new) when given."""
    out, in_control, keep_cont = [], False, False
    for raw in text.splitlines():
        s = raw.strip()
        low = s.lower()
        if low.startswith(".control"):
            in_control = True
            continue
        if low.startswith(".endc"):
            in_control = False
            continue
        if in_control or not s or s.startswith("*"):
            continue
        if s.startswith("+"):
            if keep_cont:
                out.append(s)
            continue
        keep_cont = bool(ELEMENT.match(s)) or low.startswith(KEEP_DOT)
        if keep_cont and "`" not in s and "shell" not in low:
            line = s
            for a, b in (rename or {}).items():
                line = line.replace(a, b)
            out.append(line)
        else:
            keep_cont = False
    return "\n".join(out) + "\n"

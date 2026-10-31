"""xsch.py — read xschem files as text: items, attributes, symbol lookup, xschem ROTATION. Nothing executed."""
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
    """Attributes of a property string; a key given twice keeps its FIRST value, as xschem's own lookup does
    (a pasted block of pin attributes after name=X1 must not rename the instance)."""
    out = {}
    for k, v in KV.findall(s):
        out.setdefault(k, v.strip('"'))
    return out


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



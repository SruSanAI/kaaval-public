"""analog_lib.py — write Liberty timing models of an analog cell, one per corner, for OpenSTA / OpenROAD.

    python tools/analog_lib.py <design folder> --cell "xschem/comp.sch" --arcs inp:out,en:out \
        --supplies VDD=1.8 --grounds VSS [--biases INN=0.9] [--corners tt,ss,ff] [--out libs/]

The cell is netlisted from the repository's schematic (or SPICE subcircuit "<file>#<NAME>") as text; ngspice runs our
decks around it. Each arc is input pin -> output pin; the other inputs are held at --biases.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import engine, runner  # noqa: E402
from kaaval_engine import liberty, plan as P  # noqa: E402


def kv(s):
    return {k: float(v) for k, v in (x.split("=") for x in s.split(",") if x)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--cell", required=True)
    ap.add_argument("--arcs", required=True)
    ap.add_argument("--supplies", required=True)
    ap.add_argument("--grounds", default="")
    ap.add_argument("--biases", default="")
    ap.add_argument("--corners", default="tt,ss,ff")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    ws = engine.upload(runner.design_files(a.design))
    root = os.path.join(os.path.expanduser(os.environ.get("KAAVAL_WS", "~/.kaaval/ws")), ws)
    circ = P._cell_circuit(dict(cell=a.cell), root)
    if not circ:
        sys.exit(f"{a.cell}: no such cell")
    # the cell's own netlist ends in one top-level instance whose nets are its ports; make it a subcircuit we call
    sub = circ.strip().splitlines()
    top = sub[-1].split()
    name = top[-1] if top[0].lower().startswith("x") else None
    if not name:
        sys.exit("could not find the cell's ports")
    ports = top[1:-1]
    body = "\n".join(sub[:-1])
    os.makedirs(a.out, exist_ok=True)
    for c in a.corners.split(","):
        lib = liberty.characterise(body, name, ports, kv(a.supplies), [g for g in a.grounds.split(",") if g],
                                   [tuple(x.split(":")) for x in a.arcs.split(",")], kv(a.biases), corner=c)
        path = os.path.join(a.out, f"{name}_{c}.lib")
        open(path, "w").write(lib["text"])
        print(path, "errors:" if lib["errors"] else "", *lib["errors"])


if __name__ == "__main__":
    main()

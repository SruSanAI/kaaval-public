"""silicon_twin.py — reproduce what a fabricated chip showed at one node, and say which chip context explains it.

    python tools/silicon_twin.py <design folder> --cell xschem/core_prel.sch --node Vbgr --measured 1.17,0.46 \
        --supplies VDD=1.8 --grounds VSS [--out twin.json]

Searches loads (open, 10M, 1M, 100k, 10k ohm), corners tt/ss/ff and a power-up from 0 V (step-checked). Heavy: one
power-up sweep per load; run on charger.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import engine, runner  # noqa: E402
from kaaval_engine import twin  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--cell", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--measured", required=True, help="comma-separated volts seen on silicon")
    ap.add_argument("--supplies", required=True, help="PORT=volts,...")
    ap.add_argument("--grounds", default="")
    ap.add_argument("--no-pad", action="store_true", help="the node does not leave the chip")
    ap.add_argument("--out")
    a = ap.parse_args()
    ws = engine.upload(runner.design_files(a.design))
    root = os.path.join(os.path.expanduser(os.environ.get("KAAVAL_WS", "~/.kaaval/ws")), ws)
    symptom = dict(cell=a.cell, node=a.node, measured=[float(x) for x in a.measured.split(",")],
                   supplies={k: float(v) for k, v in (s.split("=") for s in a.supplies.split(","))},
                   grounds=[g for g in a.grounds.split(",") if g], pad=not a.no_pad)
    res = twin.search(symptom, root, on_result=lambda k, r, e: print("  ran", k, "error" if e else "", flush=True))
    if not res["ok"]:
        sys.exit("; ".join(res["errors"]))
    for line in twin.explain(res):
        print(line)
    if a.out:
        json.dump(dict(symptom=symptom, **res), open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()

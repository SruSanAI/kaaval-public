"""ablation.py — does Muse Spark find what the plain review misses? Score each planner arm on labelled designs.

Each case is a design with a known answer: a fabricated chip whose silicon showed the failure, or a seeded bug (a
real design with its start-up device removed, plus the untouched original as the negative). Every arm reviews every
case through the same engine; a case counts as found when a finding of the expected rule lands on the expected cell.
Untouched designs that get a finding count as false alarms. Results go to a JSON lines file and a table.

    python tools/ablation.py cases.json --arms floor,muse,small --out ablation.jsonl

cases.json: [{"name", "root": "<local folder of the design>", "expect": [{"cell", "rule"}] or [] for negatives,
              "source": "silicon: <url>" | "seeded: <what was removed>", "split": "dev" | "heldout"}]
Only held-out cases count in the headline: development cases (the ones we looked at while building) are reported
apart, so nothing is scored on a design the prompt or checks were tuned on.
Needs MINNAL_URL / MINNAL_KEY, and MUSE_API_KEY / SMALL_API_KEY for the model arms (server environment only).
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import engine, planner, runner  # noqa: E402


def review_case(case, arm):
    root = case["root"]
    ws = engine.upload(runner.design_files(root))
    tbs = engine.testbenches(ws)
    tbr = engine.testbench(ws, tbs[0]) if tbs else None
    found = []
    if tbs and tbr and tbr.get("ok") and tbr.get("kind") == "static":
        conds = [[t, v] for t in (-40, 27, 125) for v in (0.9, 1.0, 1.1)]
        for c in ("tt", "ss", "ff", "sf", "fs"):
            engine.corner(ws, tbs[0], c, conds)
        found += [dict(rule=f["rule"], cell=tbs[0], by="designer testbench") for f in engine.analyse(ws, tbs[0])["findings"]]
    t = time.time()
    res = planner.review(arm, ws, runner.project_docs(root), runner.floor_note(tbs, tbr))
    for p in res["plans"]:
        for f in (p["result"] or {}).get("findings") or []:
            found.append(dict(rule=f["rule"], cell=p["plan"]["cell"], by=arm, message=f["message"]))
    return dict(found=found, blocks=res["blocks"], plans=[p["plan"] for p in res["plans"]], usage=res["usage"],
                seconds=round(time.time() - t, 1))


def score(case, out):
    hits = [e for e in case["expect"] if any(f["rule"] == e["rule"] and f["cell"].endswith(e["cell"]) for f in out["found"])]
    planned = [f for f in out["found"] if f["by"] != "designer testbench"]
    return dict(expected=len(case["expect"]), hit=len(hits), false_alarm=0 if case["expect"] else len(planned))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--arms", default="floor,muse")
    ap.add_argument("--out", default="ablation.jsonl")
    a = ap.parse_args()
    cases = json.load(open(a.cases))
    rows = []
    with open(a.out, "a") as fo:
        for arm in a.arms.split(","):
            if arm not in ("floor", "rules") and not planner.configured(arm):
                print(f"skip {arm}: not configured")
                continue
            for case in cases:
                try:
                    out = review_case(case, arm)
                    s = score(case, out)
                except (engine.EngineError, planner.PlannerError) as e:
                    out, s = dict(error=str(e)), dict(expected=len(case["expect"]), hit=0, false_alarm=0, error=True)
                row = dict(arm=arm, case=case["name"], source=case.get("source"), split=case.get("split", "heldout"),
                           **s, detail=out)
                rows.append(row)
                fo.write(json.dumps(row) + "\n")
                fo.flush()
                print(f"{arm:6} {case['name'][:40]:40} hit {s['hit']}/{s['expected']}  false alarms {s['false_alarm']}")
    for split in ("heldout", "dev"):
      print(f"\n[{split}] arm     found/expected   false alarms   cases")
      for arm in dict.fromkeys(r["arm"] for r in rows):
        rs = [r for r in rows if r["arm"] == arm and r.get("split", "heldout") == split]
        if not rs:
            continue
        print(f"        {arm:6}  {sum(r['hit'] for r in rs)}/{sum(r['expected'] for r in rs):<14}  "
              f"{sum(r['false_alarm'] for r in rs):<13}  {len(rs)}")


if __name__ == "__main__":
    main()

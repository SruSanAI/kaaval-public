"""layout_survey.py — layout against schematic (layout_check.compare) for every cell drawn both ways, across a folder
of cloned repositories. One JSON line per cell, resumable; prints counts only. Results on other people's designs stay
local: the table is for the designer's OK first.

    python tools/layout_survey.py CLONES OUT.jsonl
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import layout_check as L  # noqa: E402

clones, out = sys.argv[1], sys.argv[2]
done = set()
if os.path.isfile(out):
    done = {(r["repo"], r["cell"]) for r in map(json.loads, open(out))}
with open(out, "a") as f:
    for repo in sorted(os.listdir(clones)):
        root = os.path.join(clones, repo)
        if not os.path.isdir(root):
            continue
        for p in L.pairs(root):
            if (repo, p["cell"]) in done:
                continue
            t0 = time.time()
            r = L.compare(root, p)
            r.update(repo=repo, seconds=round(time.time() - t0, 2))
            f.write(json.dumps(r) + "\n")
            f.flush()
rows = [json.loads(l) for l in open(out)]
n = len(rows)
m = sum(r["match"] is True for r in rows)
x = sum(r["match"] is False for r in rows)
e = sum(r["match"] is None for r in rows)
print(f"{n} cells in {len({r['repo'] for r in rows})} repos: {m} match, {x} do not match, {e} not compared")

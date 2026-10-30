"""silicon_backtest.py — Kaaval's review on Tiny Tapeout analog chips that have silicon feedback, for a predicted-vs-
measured table with every miss and every false alarm kept.

Input: the validation set (a markdown table: row number, shuttle, project, ..., outcome; quoted silicon results) and
the folder of clones named <shuttle>__<project>, read as text (no project code is executed). Each repo gets one full
review, exactly as the server runs it (testbench, 45 conditions, the planned tests; without Muse Spark the no-model
baseline). One JSON line per row, resumable: rows already in the output are skipped.

    python tools/silicon_backtest.py SET.md CLONES OUT.jsonl [--only 20,24] [--dry]

Results on other people's designs stay local: the table that comes out of it is for the designer's OK first.
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def rows(md):
    """(n, shuttle, project, outcome) from the validation set's table."""
    out = []
    for line in open(md).read().splitlines():
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 11 or not re.fullmatch(r"\d+", cols[1]):
            continue
        proj = re.sub(r"\]\(.*", "", cols[3]).lstrip("[")
        out.append(dict(n=int(cols[1]), shuttle=cols[2], project=proj, outcome=re.sub(r"\*", "", cols[9])))
    return out


def clone_of(clones, r):
    d = os.path.join(clones, f"{r['shuttle'].lower()}__{r['project']}")
    return d if os.path.isdir(d) else None


def review(root, label):
    from app import inputs, runner, store
    rid = store.new_run(label)
    t0 = time.time()
    runner.review(rid, inputs.Source("zip", label=label), root=root)
    run, lv = store.run(rid), store.live(rid) or {}
    plans = [dict(cell=p["plan"].get("cell"), kind=p["plan"].get("kind"), findings=p.get("findings"),
                  seconds=p.get("seconds"), n=len(p.get("results") or []),
                  unconfirmed=sum(1 for x in p.get("results") or [] if str(x.get("error") or "").startswith("unconfirmed")),
                  errors=p.get("errors"))
             for p in lv.get("plan_results") or []]
    return dict(rid=rid, status=run.get("status"), seconds=round(time.time() - t0, 1),
                stages={k: (v.get("state"), v.get("dt")) for k, v in (lv.get("stages") or {}).items()},
                findings=[dict(rule=f["rule"], kind=f.get("kind"), where=f.get("location"), title=f.get("title", "")[:300])
                          for f in store.findings(rid)], plans=plans)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set_md"), ap.add_argument("clones"), ap.add_argument("out")
    ap.add_argument("--only", default=""), ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["n"] for l in open(a.out) if l.strip()}
    only = {int(x) for x in a.only.split(",") if x}
    for r in rows(a.set_md):
        if r["n"] in done or (only and r["n"] not in only):
            continue
        root = clone_of(a.clones, r)
        print(f"row {r['n']:2d} {r['shuttle']:8s} {r['project']:40s} {'clone' if root else 'NO CLONE'}", flush=True)
        if a.dry:
            continue
        rec = dict(r, clone=bool(root))
        if root:
            try:
                rec.update(review(root, f"backtest row {r['n']}: {r['project']}"))
            except Exception as e:                    # one broken repo never ends the backtest
                rec.update(status="error", error=f"{type(e).__name__}: {e}")
        with open(a.out, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print("   ", rec.get("status"), rec.get("seconds"), "s", sorted({x["rule"] for x in rec.get("findings") or []}),
              flush=True)


if __name__ == "__main__":
    main()

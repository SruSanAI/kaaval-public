"""scan.py — run the units / physical-plausibility audit over many repos (the real-world pilot).

Each repo's committed netlists and xschem schematics are audited as text (guard.sch): nothing from a third-party repo
is executed, so the scan is safe to run on any public project.

    python -m kaaval_engine.scan --projects analog_projects.json --repos repos/ --out scan.json
"""
import argparse, json, os, sys, time

from kaaval_engine import units

def scan_one(proj, repo):
    t0 = time.time()
    tiles = proj.get("tiles") or "1x2"
    r = units.audit_repo(repo, tiles)
    return dict(shuttle=proj["shuttle"], macro=proj["macro"], title=proj.get("title"), repo=proj.get("repo"),
                commit=proj.get("commit"), tiles=tiles, files=r["netlists"], devices=r["devices"],
                findings=r["findings"], seconds=round(time.time() - t0, 2))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", required=True)
    ap.add_argument("--repos", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    done = {}
    if os.path.exists(a.out):
        done = {(r["shuttle"], r["macro"]): r for r in json.load(open(a.out)) if "error" not in r}
    rows = []
    for p in json.load(open(a.projects)):
        key = (p["shuttle"], p["macro"])
        repo = os.path.join(a.repos, f"{p['shuttle']}__{p['macro']}")
        if key in done:
            rows.append(done[key])
            continue
        if not os.path.exists(os.path.join(repo, ".done")):
            rows.append(dict(shuttle=p["shuttle"], macro=p["macro"], repo=p.get("repo"), error="not fetched"))
            continue
        r = scan_one(p, repo)
        rows.append(r)
        n = {s: sum(x["severity"] == s for x in r["findings"]) for s in ("fail", "warn", "info")}
        print(f"{p['shuttle']:9} {p['macro'][:40]:40} {r['devices']:5} dev  fail {n['fail']:2} warn {n['warn']:2} "
              f"info {n['info']:2}  {r['seconds']}s", flush=True)
        json.dump(rows, open(a.out, "w"), indent=1)
    json.dump(rows, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    sys.exit(main())

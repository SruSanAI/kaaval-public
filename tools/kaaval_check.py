"""kaaval_check.py — review a local repository from the command line, as the server would, for a designer or CI.

    python tools/kaaval_check.py PATH [--sarif out.sarif] [--json out.json] [--fail-on risk|none]

Runs the whole review on PATH (read as text, nothing in it is executed): audit, layout against schematic, the
designer's testbench at 45 conditions and its feedback loops, and the planned tests (Muse Spark when MUSE_* is set,
else the no-model baseline). Prints every finding, writes them as JSON and as SARIF 2.1.0 (GitHub shows SARIF results
on the files of a pull request), and exits 1 when a design-risk warning is found (--fail-on risk, the default).
A run's records go to a temporary database unless KAAVAL_DB is set.
"""
import argparse, json, os, re, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def _file(loc, root):
    """The repository file a finding's location names (the text before ' · ', ' vs ' or ' as drawn'), if it exists."""
    head = re.split(r" · | vs | as drawn", loc or "")[0].strip().split("#")[0]
    return head if head and os.path.isfile(os.path.join(root, head)) else None


def sarif(findings, root):
    rules, results = {}, []
    for f in findings:
        rules.setdefault(f["rule"], dict(id=f["rule"], name=f["rule"].split("/")[-1],
                                         shortDescription=dict(text=f["rule"])))
        level = "note" if f.get("kind") == "note" or f.get("severity") == "info" else \
            "error" if f.get("kind") == "trap" else "warning"
        res = dict(ruleId=f["rule"], level=level, message=dict(text=f.get("title") or f["rule"]))
        p = _file(f.get("location"), root)
        if p:
            res["locations"] = [dict(physicalLocation=dict(artifactLocation=dict(uri=p)))]
        results.append(res)
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
            "runs": [dict(tool=dict(driver=dict(name="Kaaval", informationUri="https://github.com/SruSanAI/kaaval-public",
                                                rules=list(rules.values()))), results=results)]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kaaval review of a local repository")
    ap.add_argument("path"), ap.add_argument("--sarif"), ap.add_argument("--json")
    ap.add_argument("--fail-on", choices=["risk", "none"], default="risk")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.path)
    if not os.path.isdir(root):
        ap.error(f"{root} is not a folder")
    os.environ.setdefault("KAAVAL_DB", os.path.join(tempfile.mkdtemp(prefix="kaaval_"), "kaaval.db"))
    from app import inputs, runner, store                # (after KAAVAL_DB is set)
    rid = store.new_run(f"kaaval_check {os.path.basename(root)}")
    runner.review(rid, inputs.Source("zip", label=os.path.basename(root)), root=root)
    run, fs = store.run(rid), store.findings(rid)
    events = store.events(rid)
    for e in events:
        if e.get("level") in ("warn", "error"):
            print(f"[{e['stage']}] {e['msg']}", file=sys.stderr)
    order = {"trap": 0, "risk": 1, "note": 2}
    for f in sorted(fs, key=lambda f: (order.get(f.get("kind"), 3), f["rule"])):
        print(f"{f.get('kind', ''):5} {f['rule']:28} {f.get('location', '')}\n      {f.get('title', '')[:400]}")
    risks = [f for f in fs if f.get("kind") == "risk" and f.get("severity") == "warn"]
    print(f"\nKaaval: {len(fs)} finding(s), {len(risks)} design-risk warning(s), status {run.get('status')}")
    if a.json:
        json.dump(dict(status=run.get("status"), findings=fs, events=events), open(a.json, "w"), indent=1, default=str)
    if a.sarif:
        json.dump(sarif(fs, root), open(a.sarif, "w"), indent=1)
    return 1 if a.fail_on == "risk" and risks else 0


if __name__ == "__main__":
    sys.exit(main())

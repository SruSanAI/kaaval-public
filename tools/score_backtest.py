"""score_backtest.py — the silicon backtest's table from tools/silicon_backtest.py output and the scope labels.

Every row is kept: in-scope failures (did a review finding point at it?), working chips (every design-risk finding is a
candidate false alarm until a person reads it), out of scope (listed, not scored). Coverage per row: tests run,
conditions left unconfirmed, errors, minutes. Nothing here decides that a finding is right; it counts what was said.

    python tools/score_backtest.py OUT.jsonl bench/silicon_scope.json > backtest.md
"""
import json, sys

RELEVANT = {  # the rules that could explain each kind of in-scope silicon problem
    "stability": {"analog/unstable", "analog/low_phase_margin", "analog/oscillates"},
    "supply": {"analog/overstress", "analog/sequence_dependent"},
    "load": {"analog/weak_output"},
    "start": {"analog/no_startup", "analog/two_states", "analog/marginal_startup", "analog/sequence_dependent"},
}


def kinds(label):
    l = label.lower()
    return [k for k, w in (("stability", ("stabil", "phase margin")), ("supply", ("supply", "domain")),
                           ("load", ("load", "output")), ("start", ("start", "bistable", "stuck", "operating point")))
            if any(x in l for x in w)]


def main(out, scope_path):
    recs = {}
    for l in open(out):
        if l.strip():
            r = json.loads(l)
            recs[str(r["n"])] = r
    sc = json.load(open(scope_path))
    risk = lambda r: [f for f in r.get("findings") or [] if f.get("kind") == "risk"]
    trap = lambda r: [f for f in r.get("findings") or [] if f.get("kind") == "trap"]
    cov = lambda r: (f"{len(r.get('plans') or [])} tests, {sum(p.get('unconfirmed') or 0 for p in r.get('plans') or [])} "
                     f"unconfirmed, {(r.get('seconds') or 0) / 60:.0f} min" if r.get("status") == "done"
                     else "not run" if not r else r.get("status") or ("no clone" if not r.get("clone") else "not run"))
    print(f"Of {len(sc['in_scope_fail']) + len(sc['works']) + len(sc['out_of_scope'])} chips with silicon feedback, "
          f"{len(sc['in_scope_fail'])} failed in a way Kaaval checks, {len(sc['works'])} work, and "
          f"{len(sc['out_of_scope'])} had problems Kaaval does not check (mostly frequency or level accuracy) or an "
          f"unknown cause. Counts only: on {len(sc['in_scope_fail'])} chips one hit or miss moves a percentage by "
          f"{100 / len(sc['in_scope_fail']):.0f} points, so none is given. Scope labels are the Kaaval author's reading "
          f"of each outcome, not the designers'.\n")
    print("## In-scope silicon failures\n\n| # | project | silicon | Kaaval findings | relevant | coverage |\n|---|---|---|---|---|---|")
    hit = ran = 0
    for n, why in sorted(sc["in_scope_fail"].items(), key=lambda x: int(x[0])):
        r = recs.get(n, {})
        rules = sorted({f["rule"] for f in risk(r)})
        want = set().union(*[RELEVANT[k] for k in kinds(why)]) if kinds(why) else set()
        rel = sorted(set(rules) & want)
        if r.get("status") == "done":
            ran += 1
            hit += bool(rel)
        print(f"| {n} | {r.get('project', '?')} | {why} | {', '.join(rules) or 'none'} | {', '.join(rel) or '-'} | {cov(r)} |")
    print(f"\nFlagged with a relevant rule: **{hit} of {ran}** reviewed ({len(sc['in_scope_fail'])} in scope).\n")
    print("## Working chips (false-alarm check)\n\n| # | project | design-risk findings | traps | coverage |\n|---|---|---|---|---|")
    fa = rn = 0
    for n in sorted(sc["works"], key=int):
        r = recs.get(n, {})
        rules = sorted({f["rule"] for f in risk(r)})
        if r.get("status") == "done":
            rn += 1
            fa += bool(rules)
        print(f"| {n} | {r.get('project', '?')} | {', '.join(rules) or 'none'} | {len(trap(r))} | {cov(r)} |")
    print(f"\nWorking chips with at least one design-risk finding: **{fa} of {rn}** reviewed (each to be read: a finding "
          f"on a working chip is a false alarm or a margin the bench never exercised).\n")
    print("## Out of scope (not scored)\n")
    for n, why in sorted(sc["out_of_scope"].items(), key=lambda x: int(x[0])):
        r = recs.get(n, {})
        print(f"- {n} {r.get('project', '')}: {why}; findings: {', '.join(sorted({f['rule'] for f in risk(r)})) or 'none'}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

"""check_netlister.py — measure guard.netlist against netlists that xschem itself wrote, across many repos.

For every committed .spice whose header names its schematic (`** sch_path: .../x.sch`) and whose schematic is in the
repo, both netlists are compared device by device: same element name, model and nets in pin order. Nets xschem named
automatically (net1, net2, ...) are matched as wildcards, since their numbering is arbitrary. Committed netlists can
be older than their schematic, so a mismatch is a lower bound on our accuracy, not proof of an error.

    python tools/check_netlister.py <folder of cloned repos>
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import netlist as N  # noqa: E402
from kaaval_engine.units import logical_lines  # noqa: E402

AUTO = re.compile(r"^net\d+$", re.I)


def devices(lines):
    """{(subckt, element name): (model, nets)} — names repeat across subcircuits, so the subckt is part of the key."""
    out, sub = {}, ""
    for t in lines:
        p = t.split()
        if not p:
            continue
        low = p[0].lower()
        if low == ".subckt" and len(p) > 1:
            sub = p[1].lower()
            continue
        if low == ".ends":
            sub = ""
            continue
        if low[0] not in "xmdrcvil":
            continue
        mi = next((i for i, w in enumerate(p) if w.startswith("sky130_fd_pr__")), None)
        if mi is None:
            continue
        out[(sub, low)] = (p[mi], p[1:mi])
    return out


def same(a, b):
    if a[0] != b[0] or len(a[1]) != len(b[1]):
        return False
    return all(x == y or AUTO.match(x) or AUTO.match(y) or x.lower() == y.lower() for x, y in zip(a[1], b[1]))


def main(root):
    files = ok = dev_total = dev_ok = 0
    worst = []
    for repo in sorted(os.listdir(root)):
        rd = os.path.join(root, repo)
        for d, dirs, fs in os.walk(rd):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in fs:
                if not f.endswith(".spice"):
                    continue
                path = os.path.join(d, f)
                head = open(path, errors="replace").read(400)
                m = re.search(r"\*\* sch_path: (\S+\.sch)", head)
                if not m:
                    continue
                name = os.path.basename(m.group(1))
                cand = [os.path.join(dd, name) for dd, _, ff in os.walk(rd) if name in ff]
                if not cand:
                    continue
                try:
                    ours = devices(N.netlist(cand[0]).splitlines())
                except Exception as e:      # a parser crash counts as a full miss
                    ours = {}
                ref = devices([t for _, t in logical_lines(path)])
                # count only what came from a schematic: the top level and subcircuits that have a .sch in the repo
                # (xschem also pastes library netlists, e.g. standard cells, which no schematic describes)
                schs = {os.path.splitext(f)[0].lower() for dd, _, ff in os.walk(rd) for f in ff if f.endswith(".sch")}
                ref = {k: v for k, v in ref.items() if k[0] == "" or k[0] in schs}
                if not ref:
                    continue
                # xschem's "netlist as subcircuit" mode wraps the whole top in .subckt <schematic name>; ours is flat
                top = os.path.splitext(name)[0].lower()
                if any(k[0] == top for k in ref) and not any(k[0] == top for k in ours):
                    ours = {((top if k[0] == "" else k[0]), k[1]): v for k, v in ours.items()}
                files += 1
                hit = sum(1 for k, v in ref.items() if k in ours and same(v, ours[k]))
                dev_total += len(ref)
                dev_ok += hit
                ok += hit == len(ref)
                if hit < len(ref):
                    worst.append((len(ref) - hit, os.path.relpath(path, root)))
    print(f"{files} xschem netlists compared; {ok} identical ({100 * ok / max(1, files):.1f} %); "
          f"devices {dev_ok}/{dev_total} ({100 * dev_ok / max(1, dev_total):.1f} %)")
    for n, p in sorted(worst, reverse=True)[:12]:
        print(f"  {n:4} devices differ  {p}")


if __name__ == "__main__":
    main(sys.argv[1])

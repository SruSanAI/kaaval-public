"""runner.py — one Kaaval review run, streamed live: fetch -> audit -> testbench -> nominal -> PVT -> review.

Nothing from the repository is executed: it arrives as files (shallow git fetch without GDS/OASIS, or a .zip) and
its text files are handed to Kaaval's review engine (app/engine.py -> kaaval_engine, in this process), which reads them as text
and simulates only decks it builds itself. This module orchestrates and keeps the live state for the bench.

While it runs, a `live` state is kept for the bench UI: per-stage timing, the PVT grid (one cell per corner x
temperature x supply, filled as each simulation lands), the worst operating margin per device mapped onto the
designer's own schematic names, and that schematic as SVG.
"""
import itertools, os, re, shutil, subprocess, threading, time

from app import engine, inputs, planner, sizing, store
from guard import sch_svg
from kaaval_engine import extract, layout_check, netlist, postlayout, sim
from kaaval_engine import plan as kplan

WORK = os.path.expanduser(os.environ.get("KAAVAL_WORK", "~/.kaaval/repos"))
MAX_REPO_MB = 300
STAGES = ["fetch", "audit", "testbench", "nominal", "pvt", "muse", "review"]
STAGE_NAMES = {"fetch": "Fetch", "audit": "Units audit", "testbench": "Testbench", "nominal": "Operating point",
               "pvt": "PVT sweep", "muse": "Muse Spark review", "review": "Review"}


def _git(args, cwd, timeout=180):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


# only what Kaaval reads: schematics, symbols, netlists, project metadata and docs (never GDS/OASIS or binaries), and
# the top-level Verilog under src/ for the chip view (read as text to draw the tile, never compiled or run)
WANT = ["*.sch", "*.sym", "*.spice", "*.sp", "*.cir", "*.spi", "*.net", "*.lib", "info.yaml", "*.md", "*.yaml",
        "*.yml", "xschemrc", "*.mag", "/src/*.v", "/src/*.sv"]


def fetch(rid, src):
    """Shallow, tree-only clone; then the wanted file types are checked out in one batched fetch."""
    d = os.path.join(WORK, rid)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    _git(["init", "-q"], d)
    _git(["remote", "add", "origin", src.url], d)
    _git(["config", "core.sparseCheckout", "true"], d)
    _git(["sparse-checkout", "set", "--no-cone", *WANT], d)
    ref = src.ref or "HEAD"
    r = _git(["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", ref], d)
    if r.returncode and src.ref and not src.ref.startswith("refs/"):
        r = _git(["fetch", "-q", "--filter=blob:none", "origin", src.ref], d)   # a bare sha may need a deeper fetch
    if r.returncode:
        raise RuntimeError("Could not fetch it. Is the repository public and the branch/commit right?")
    r = _git(["checkout", "-q", "FETCH_HEAD"], d, timeout=300)
    if r.returncode:
        raise RuntimeError("Fetched the history but could not check out the design files.")
    sha = _git(["rev-parse", "HEAD"], d).stdout.strip()
    _size_ok(d)
    return d, sha


def _size_ok(d):
    size = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(d) for f in fs) / 1e6
    if size > MAX_REPO_MB:
        raise RuntimeError(f"The project is {size:.0f} MB, above the {MAX_REPO_MB} MB limit.")


def tiles_of(repo):
    for base in (repo, os.path.dirname(repo)):
        p = os.path.join(base, "info.yaml")
        if os.path.exists(p):
            m = re.search(r"^\s*tiles:\s*\"?(\d+x\d+)", open(p, errors="replace").read(), re.M)
            if m:
                return m.group(1)
    return "1x2"


CORNERS, TEMPS, VSCALES = ["tt", "ss", "ff", "sf", "fs"], [-40, 27, 125], [0.9, 1.0, 1.1]
NOMINAL = ("tt", 27, 1.0)
TEXT_EXT = (".sch", ".sym", ".spice", ".sp", ".cir", ".spi", ".net", ".lib", ".yaml", ".yml", ".md", ".mag")


def margin(d):
    return abs(d.get("vds") or 0.0) - abs(d.get("vdsat") or 0.0)


def design_files(root):
    """{relative path: text} of the design files the engine reads (never binaries)."""
    out = {}
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in fs:
            if f.endswith(TEXT_EXT) or f == "xschemrc":
                p = os.path.join(d, f)
                if os.path.getsize(p) < 8_000_000:
                    out[os.path.relpath(p, root)] = open(p, errors="replace").read()
    return out


def map_device(simname, inst):
    """Simulated device (x1.xm2, x1.x1.xm11) -> the name drawn on the DUT schematic (M2, x1), or None."""
    parts = simname.lower().split(".")
    if not inst or parts[0] != inst.lower() or len(parts) < 2:
        return None
    return parts[1]


class Live:
    """The bench UI's state for one run, persisted as it changes."""

    def __init__(self, rid):
        self.rid = rid
        self.d = dict(stages={s: {"state": "pending"} for s in STAGES}, cells=[], devices={}, svg="",
                      testbench="", dut="", source="", grid=dict(corners=CORNERS, temps=TEMPS, vscales=VSCALES))
        self.lock = threading.Lock()

    def save(self):
        store.set_live(self.rid, self.d)

    def stage(self, s, state, note=""):
        with self.lock:
            st = self.d["stages"][s]
            if state == "running":
                st["t0"] = time.time()
            if state in ("done", "error", "skipped"):
                st["dt"] = round(time.time() - st.get("t0", time.time()), 1)
            st["state"], st["note"] = state, note
            self.save()
        store.update_run(self.rid, stage=s)

    def set(self, **kw):
        with self.lock:
            self.d.update(kw)
            self.save()


POST_BUDGET = float(os.environ.get("KAAVAL_POST_BUDGET", "300") or 0)     # seconds for the as-drawn re-runs; 0 = none


def post_layout(rid, lv, root, files, lay, max_cells=3):
    """The circuit as drawn: for cells whose layout matched their schematic (layout_check), the power-up and
    stability tests the review ran on the schematic run again, unchanged, on the layout extracted with its
    capacitances (postlayout); a disagreement is a finding, agreement is said."""
    ok = {r["sch"]: r for r in lay or [] if r.get("verdict") in ("match", "sizes differ")}
    todo = [(k, pr) for k, pr in enumerate(lv.d.get("plan_results") or [])
            if pr.get("ok") and pr["plan"].get("cell") in ok and pr["plan"].get("kind") in ("powerup", "stability")]
    # a test that leaves an input undriven says nothing as drawn: where a floating input settles depends on the very
    # capacitance the layout adds (in a pilot, all three 'differences' were such inputs). Muse Spark's plans bias them
    floating = {}
    for k, pr in todo:
        try:
            u = kplan.undriven(pr["plan"], root)
        except Exception:                                   # noqa: BLE001 - an unreadable cell is simply not compared
            u = ["?"]
        if u:
            floating[pr["plan"]["cell"]] = u
    if floating:
        store.event(rid, "muse", f"Not compared as drawn ({len(floating)} cell(s)): their tests leave inputs undriven "
                                 f"(e.g. {next(iter(floating))}: {', '.join(next(iter(floating.values()))[:4])}), and "
                                 f"a floating input settles wherever the layout's capacitance puts it. A planned test "
                                 f"that biases them (Muse Spark) is compared.", "info")
    todo = [(k, pr) for k, pr in todo if pr["plan"]["cell"] not in floating]
    cells = list(dict.fromkeys(pr["plan"]["cell"] for _, pr in todo))[:max_cells]
    todo = [(k, pr) for k, pr in todo if pr["plan"]["cell"] in cells]
    if not todo:
        return
    extra = {}
    for c in cells:
        r = ok[c]
        text, err = extract.cell(root, r["cell"], r["mag"], parasitics=True)
        if text:
            extra[postlayout.post_path(r["cell"])] = text
        else:
            store.event(rid, "muse", f"{r['cell']}: post-layout extraction failed ({err})", "warn")
    if not extra:
        return
    ws2 = engine.upload(dict(files, **extra))
    agree = []
    clock = planner.Clock(POST_BUDGET)
    for i, (k, pr) in enumerate(todo):
        r = ok[pr["plan"]["cell"]]
        if postlayout.post_path(r["cell"]) not in extra:
            continue
        try:
            res = planner.run_plan(ws2, dict(pr["plan"], cell=postlayout.post_cell(r["cell"])), clock,
                                   [p["plan"] for _, p in todo[i + 1:]])
        except engine.EngineError as e:
            res = dict(ok=False, errors=[str(e)])
        if res.get("skipped"):
            store.event(rid, "muse", f"{r['cell']} ({pr['plan']['kind']}): not compared as drawn: the post-layout "
                                     f"time budget ({POST_BUDGET:.0f} s) was spent", "info")
            continue
        if not res.get("ok"):
            store.event(rid, "muse", f"{r['cell']} ({pr['plan']['kind']}): the post-layout test could not run: "
                                     f"{'; '.join(res.get('errors') or [])[:300]}", "warn")
            continue
        kind = pr["plan"]["kind"]
        diffs = postlayout.compare(kind, pr.get("results") or [], res.get("results") or [])
        n = len([x for x in pr.get("results") or [] if not x.get("error")])
        f = postlayout.finding(r["cell"], kind, diffs, n)
        if f:
            store.add_finding(rid, dict(f, kind="risk", location=f"{r['mag']} as drawn, with its capacitance, vs "
                                                                  f"{r['sch']}"))
        else:
            agree.append(f"{r['cell']} ({kind})")
    if agree:
        store.event(rid, "muse", "As drawn, with the capacitance its layout adds, these give the same result as their "
                                 "schematic at every condition both completed: " + ", ".join(agree))


def keep_plans(rid, lv, res, by):
    """Store each planned test's results for the bench's evidence views, and its findings as findings."""
    kept, nf, nu, ns = list(lv.d.get("plan_results") or []), 0, 0, 0
    for pr in res["plans"]:
        r = pr["result"] or {}
        k = len(kept)
        kept.append(dict(plan=pr["plan"], by=by, ok=r.get("ok"), errors=r.get("errors"), results=r.get("results") or [],
                         findings=[f["rule"] for f in r.get("findings") or []], seconds=r.get("seconds")))
        if r.get("seconds") is not None:
            store.event(rid, "muse", f"{pr['plan']['cell']} ({pr['plan']['kind']}): {len(r.get('results') or [])} "
                                     f"conditions in {r['seconds']:.0f} s")
        rows = r.get("results") or []
        unc = [x for x in rows if str(x.get("error") or "").startswith("unconfirmed")]
        over = [x for x in rows if x.get("error") == sim.OVER] if not r.get("skipped") else []
        nu += len(unc) + len(over)
        if r.get("skipped"):
            ns += 1
        if over:
            store.event(rid, "muse", f"{pr['plan']['cell']} ({pr['plan']['kind']}): {len(over)}/{len(rows)} conditions "
                                     f"not run: the review's time budget was spent. They count as not tested.", "warn")
        if unc:
            store.event(rid, "muse", f"{pr['plan']['cell']} ({pr['plan']['kind']}): {len(unc)}/{len(rows)} conditions "
                                     f"not checked against a finer time step: {unc[0]['error'].split(', so')[0][13:]}. "
                                     f"They count as not tested, not as findings.", "warn")
        for f in r.get("findings") or []:
            nf += 1
            store.add_finding(rid, dict(rule=f["rule"], severity=f["severity"],
                                        kind="note" if f["severity"] == "info" else "risk", title=f["message"],
                                        location=f"{pr['plan']['cell']} · " + ("test planned by Muse Spark" if by == "muse"
                                                                               else "baseline power-up (no model)"),
                                        device=f.get("device", ""), detail=dict(f, plan=pr["plan"], planner=by, k=k)))
    lv.set(plan_results=kept, unconfirmed=lv.d.get("unconfirmed", 0) + nu, not_run=lv.d.get("not_run", 0) + ns)
    return nf


LOOP_BUDGET = float(os.environ.get("KAAVAL_LOOP_BUDGET", "240"))   # seconds for the testbench loops of one review
LOOP_TBS = 8


def testbench_loops(rid, ws, tbs):
    """Every feedback loop the designer's testbenches close around an instance (a follower, an inverting stage, a
    regulator's divider), its loop gain measured at 45 conditions: the loop the chip will run, in the configuration
    its designer chose. The same subcircuit in the same feedback in several testbenches is reported once."""
    t0, said, n = time.time(), {}, 0
    for rel in tbs[:LOOP_TBS]:
        left = LOOP_BUDGET - (time.time() - t0)
        if left < 5:
            store.event(rid, "testbench", f"Testbench loops: time budget ({LOOP_BUDGET:.0f} s) spent; "
                                          f"{len(tbs[:LOOP_TBS]) - tbs.index(rel)} testbench(es) not checked", "warn")
            break
        try:
            res = engine.loops(ws, rel, budget=left)
        except engine.EngineError as e:
            store.event(rid, "testbench", f"{rel}: its feedback loops could not be checked ({e})", "warn")
            continue
        for lp in res.get("loops") or []:
            pms = [r["pm"] for r in lp["results"] if r.get("pm") is not None]
            ok = sum(1 for r in lp["results"] if not r.get("error"))
            what = f"{lp['inst']} ({lp['subckt']}) in feedback, its output {lp['net']} {lp['via']}"
            key = (lp["subckt"].lower(), tuple(sorted(f["rule"] for f in lp["findings"])),
                   round(min(pms)) if pms else None)
            if key in said:
                said[key].append(rel)
                continue
            said[key] = [rel]
            store.event(rid, "testbench", f"{rel}: {what}: " + (
                f"an amplifier loop at {ok}/{len(lp['results'])} conditions" +
                (f", phase margin {min(pms):.0f}–{max(pms):.0f}°" if pms else ", no unity-gain crossing")
                if ok else f"not judged ({lp.get('not_judged') or 'no condition simulated'})"))
            for f in lp["findings"]:
                n += 1
                store.add_finding(rid, dict(rule=f["rule"], severity=f["severity"], kind="risk", device=lp["inst"],
                                            title=f"In the designer's own testbench, {what}. " + f["message"],
                                            location=f"{rel} · {lp['inst']} loop (cut at {lp['pin']})",
                                            detail=dict(f, loop={k: lp[k] for k in ("inst", "subckt", "net", "pin",
                                                                                     "via")}, testbench=rel,
                                                        results=lp["results"])))
    for key, rels in said.items():
        if len(rels) > 1:
            store.event(rid, "testbench", f"The {key[0]} loop above is the same in {len(rels)} testbenches "
                                          f"({', '.join(rels[:4])}): reported once")
    return n


def unc_note(lv):
    """The coverage gap of the planned tests, for the stage line: conditions whose fine-step check could not run."""
    n, k = lv.d.get("unconfirmed") or 0, lv.d.get("not_run") or 0
    return ((f" · {n} condition(s) not confirmed (not tested)" if n else "") +
            (f" · {k} test(s) not run (time budget)" if k else ""))


NO_3V3 = "the chip has no 3.3 V supply"


def chip_supplies(root):
    """Which supplies the chip itself gives the design, from the Tiny Tapeout top level (src/*.v, read as text):
    a wrapper with VPWR / VDPWR and no VAPWR has only the 1.8 V supply → a line for the planner, or ""."""
    names = set()
    for d in ("src", "verilog"):
        dd = os.path.join(root, d)
        if os.path.isdir(dd):
            for f in sorted(os.listdir(dd)):
                if f.endswith((".v", ".sv")):
                    txt = open(os.path.join(dd, f), errors="replace").read(200_000)
                    # the wrapper is the module that takes the chip's power pins as ports
                    names |= {m[1].upper() for m in re.findall(r"(?i)\b(input|inout)\s+(?:wire\s+)?(VPWR|VDPWR|VAPWR)\b", txt)}
    if names and "VAPWR" not in names:
        return (f"## Tiny Tapeout power pins (src/*.v)\nThe top level has {', '.join(sorted(names))} and no VAPWR: "
                f"{NO_3V3}; every block runs from the 1.8 V supply.")
    return ""


def project_docs(root):
    """README and Tiny Tapeout docs, the designer's own words about the design (text, capped), and the supplies the
    chip's top level declares."""
    out = []
    for rel in ("README.md", "docs/info.md", "info.yaml"):
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            out.append(f"## {rel}\n" + open(p, errors="replace").read()[:8000])
    sup = chip_supplies(root)
    if sup:
        out.append(sup)
    return "\n\n".join(out)


def floor_note(tbs, tbr):
    """What the plain review did with the designer's testbenches, for the planner to read."""
    if not tbs:
        return "No testbench was found in the repository."
    lines = [f"Testbenches found: {', '.join(tbs[:12])}" + (" ..." if len(tbs) > 12 else ""),
             f"Reviewed: {tbs[0]}"]
    if tbr:
        lines.append(f"Kind: {tbr.get('kind')} ({tbr.get('reason', '')})")
        if not tbr.get("ok"):
            lines.append(f"It did not simulate: {tbr.get('error')}")
    return "\n".join(lines)


def review(rid, src, root=None):
    t0 = time.time()
    lv = Live(rid)
    try:
        store.update_run(rid, status="running")
        lv.set(source=src.describe())
        lv.stage("fetch", "running")
        if root is None:
            store.event(rid, "fetch", f"Fetching {src.describe()}: files only, GDS skipped, nothing executed")
            root, sha = fetch(rid, src)
        else:
            sha = "upload"
        store.update_run(rid, commit_sha=sha)
        scope = os.path.join(root, src.path) if src.path else root
        if not os.path.isdir(scope):
            raise RuntimeError(f"The folder '{src.path}' is not in the repository.")
        files = design_files(root)
        layout_note = None
        if extract.needed(files):               # layout only: a netlist from the layout, so there is something to simulate
            text, layout_note = extract.from_layout(root)
            if text:
                files[f"{extract.OUT}/{extract.top_cell(root)[0]}.spice"] = text
        ws = engine.upload(files)
        lv.set(ws=ws)
        lv.stage("fetch", "done", sha[:7])
        store.event(rid, "fetch", f"Got {('commit ' + sha[:7]) if sha != 'upload' else 'the uploaded files'}; "
                                  f"{len(files)} design files handed to the review engine")
        if layout_note:
            store.event(rid, "fetch", layout_note, "info" if f"{extract.OUT}/" in "".join(files) else "warn")

        lv.stage("audit", "running")
        rel_scope = os.path.relpath(scope, root) if scope != root else ""
        a = engine.audit(ws, rel_scope, tiles_of(scope))
        # the same trap usually appears in several files (schematic, testbench netlist, extracted netlist):
        # one finding per (rule, value) with every location, as a reviewer would report it
        groups = {}
        for x in a["findings"]:
            if x["severity"] == "info":
                continue
            raw = x["message"].split(" reads as ")[0].split("=")[-1].strip()
            try:
                raw = f"{float(raw):g}"                 # 1e12 and 1e+12 are the same value
            except ValueError:
                pass
            key = (x["rule"], raw)
            groups.setdefault(key, []).append(x)
        n_units = len(groups)
        for (rule, _), xs in groups.items():
            x = xs[0]
            devs = sorted({y.get("device", "").lstrip("Xx") for y in xs if y.get("device")})
            files = sorted({y["file"] for y in xs})
            store.add_finding(rid, dict(rule=f"units/{rule}", severity=x["severity"], kind="trap",
                                        title=x["message"].split(";")[0][:160] + (f" ({len(devs)} devices)" if len(devs) > 1 else ""),
                                        location=", ".join(f"{y['file']}:{y['line']}" for y in xs[:3]) +
                                        (f" and {len(xs) - 3} more" if len(xs) > 3 else ""),
                                        device=devs[0] if devs else "", detail=dict(x, devices=devs, files=files,
                                                                                    occurrences=len(xs))))
        try:                                   # parts whose symbol is not in the repository are in no simulation
            miss = netlist.missing_symbols(root)
        except OSError:
            miss = {}
        if miss:
            where = sorted({s for v in miss.values() for s in v})
            store.event(rid, "audit", f"{sum(len(v) for v in miss.values())} component(s) use a symbol the repository "
                                      f"does not contain ({', '.join(os.path.basename(k) for k in list(miss)[:4])}"
                                      f"{', ...' if len(miss) > 4 else ''}; in {', '.join(where[:3])}"
                                      f"{', ...' if len(where) > 3 else ''}): those parts are missing from every "
                                      "simulation of these schematics, so their results describe an incomplete circuit.",
                        "warn")
        lay, lay_f, lay_note = layout_check.review(root)       # the layout against the schematic it should build
        for f in lay_f:
            store.add_finding(rid, dict(f, kind="note" if f["severity"] == "info" else "risk"))
        if lay_note:
            store.event(rid, "audit", lay_note, "warn" if lay_f else "info")
        lv.stage("audit", "done", f"{a['devices']} devices · {n_units} trap(s)"
                 + (f" · {len(lay_f)} layout mismatch(es)" if lay else ""))
        store.event(rid, "audit", f"Read {a['netlists']} schematics/netlists ({a['devices']} devices) as text; "
                                  f"{n_units} units trap(s)")

        lv.stage("testbench", "running")
        tbs = engine.testbenches(ws, rel_scope, src.focus)
        if not tbs:
            lv.stage("testbench", "skipped", "none found")
            for s in ("nominal", "pvt"):
                lv.stage(s, "skipped")
            # say plainly what the repository holds, so a design that cannot be reviewed is never a silent blank
            try:
                cells = engine.cells(ws)
            except engine.EngineError:
                cells = []
            kinds = {}
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                kinds[ext] = kinds.get(ext, 0) + 1
            if cells:
                spice = sum(1 for c in cells if "#" in c["cell"])
                store.event(rid, "testbench", f"No testbench in this design; {len(cells)} circuit cell(s) found"
                            + (f" ({spice} from SPICE netlists)" if spice else "") +
                            ". Muse Spark plans their tests (power-up, stability) when it is connected.", "warn")
            else:
                held = ", ".join(f"{n} {e or 'other'}" for e, n in sorted(kinds.items(), key=lambda x: -x[1])[:4])
                store.event(rid, "testbench", "Nothing Kaaval can simulate here: no xschem schematic with ports and no "
                            f"SPICE subcircuit (the design files are: {held or 'none'}). Layout-only designs (Magic, "
                            "GDS) need an extracted netlist committed to the repository.", "error")
        else:
            rel = tbs[0]
            lv.stage("nominal", "running")
            fixed = n_units > 0       # simulate the circuit as the silicon is drawn, not as the trap makes it
            tbr = engine.testbench(ws, rel, fixed)
            lv.set(corrected=tbr.get("corrections", []))
            if tbr.get("corrections"):
                ch = tbr["corrections"]
                store.event(rid, "testbench", f"Simulating with the units trap corrected ({len(ch)} device(s), e.g. "
                            f"{ch[0]['device']} {ch[0]['before']} → {ch[0]['after']}), so every result below describes the "
                            "circuit as drawn, not the trap.")
            inst, dut = tbr.get("dut_inst"), tbr.get("dut")
            svg = sch_svg.render(os.path.join(root, dut or rel))
            lv.set(testbench=rel, dut=dut or rel, svg=svg, dut_inst=inst or "")
            lv.stage("testbench", "done", os.path.basename(rel))
            store.event(rid, "testbench", f"Testbench {rel}" + (f" exercises {dut} (instance {inst})" if dut else "")
                        + (f"; {len(tbs) - 1} more found" if len(tbs) > 1 else ""))
            lv.set(kind=tbr.get("kind", "static"), kind_reason=tbr.get("reason", ""))
            if tbr.get("kind") == "dynamic" and not (tbr.get("outputs") and tbr.get("window")):
                lv.stage("nominal", "skipped", "switching circuit")
                lv.stage("pvt", "skipped", "no outputs to measure")
                store.event(rid, "nominal", "Switching circuit: " + tbr.get("reason", "") + ". No output net or "
                            "transient analysis to measure, so no switching checks were run.", "warn")
            elif tbr.get("kind") == "dynamic":
                outs = tbr["outputs"]
                store.event(rid, "nominal", "Switching circuit: " + tbr.get("reason", "") + ". Resting-point checks "
                            "do not apply; instead the designer's own transient runs at every corner, and each output "
                            f"({', '.join(outs)}) must keep doing what it does at nominal.")
                conds = [[t, v] for t in TEMPS for v in VSCALES]
                nomr = engine.tcorner(ws, rel, "tt", conds, fixed)
                nom = next((r for r in nomr if (r["temp"], r["vscale"]) == (27, 1.0)), None)
                if not nom or nom["error"]:
                    lv.stage("nominal", "error", (nom or {}).get("error", "no result"))
                    lv.stage("pvt", "skipped")
                    store.event(rid, "nominal", f"The designer's transient did not run: {(nom or {}).get('error')}"
                                + (f" {tbr['include_note']}" if tbr.get("include_note") else ""), "error")
                else:
                    n0 = nom["outputs"]
                    desc = "; ".join(f"{k} {v['freq'] / 1e6:.3g} MHz" if v["freq"] > 0 else f"{k} {v['mean']:.3f} V"
                                     for k, v in n0.items())
                    lv.set(nominal_outputs=n0)
                    lv.stage("nominal", "done", desc[:60])
                    store.event(rid, "nominal", f"At tt, 27 °C, nominal supply: {desc}")
                    lv.stage("pvt", "running", "0 / 45")
                    done = [0]

                    def cell_of(c, r):
                        cell = dict(corner=c[0], temp=c[1], vscale=c[2])
                        if r["error"] or not r["outputs"]:
                            return dict(cell, status="err", note=r["error"] or "no waveform")
                        bad = []
                        for k, v0 in n0.items():
                            v = r["outputs"].get(k)
                            if not v:
                                continue
                            if v0["freq"] > 0 and v0["pp"] > 0.3:
                                if not (v["freq"] > 0 and v["pp"] > 0.3 * v0["pp"]):
                                    bad.append(f"{k} stops switching")
                            elif abs(v["mean"] - v0["mean"]) > 0.25 * max(abs(v0["mean"]), 0.1):
                                bad.append(f"{k} {v0['mean']:.2f} → {v['mean']:.2f} V")
                        return dict(cell, status="warn" if bad else "ok", n_triode=len(bad), devices=bad,
                                    outputs=r["outputs"])

                    def add(c, r):
                        with lv.lock:
                            lv.d["cells"].append(cell_of(c, r))
                            done[0] += 1
                            lv.d["stages"]["pvt"]["note"] = f"{done[0]} / 45"
                            lv.save()

                    for r in nomr:
                        add(("tt", r["temp"], r["vscale"]), r)

                    def run_tcorner(k):
                        for r in engine.tcorner(ws, rel, k, conds, fixed):
                            add((k, r["temp"], r["vscale"]), r)

                    ths = [threading.Thread(target=run_tcorner, args=(k,)) for k in CORNERS if k != "tt"]
                    for th in ths:
                        th.start()
                    for th in ths:
                        th.join()
                    an = engine.tanalyse(ws, rel)
                    for f in an["findings"]:
                        store.add_finding(rid, dict(rule=f["rule"], severity=f["severity"],
                                                    kind="note" if f["severity"] == "info" else "risk",
                                                    title=f["message"][:220], location=f"{rel} · {f['device']}",
                                                    device="", detail=dict(f, corrected=bool(tbr.get("corrections")))))
                    lv.set(spread=an.get("spread", {}))
                    for k, sp in an.get("spread", {}).items():
                        store.event(rid, "pvt", (f"{k}: {sp['lo'] / 1e6:.3g}–{sp['hi'] / 1e6:.3g} MHz across PVT "
                                                 f"(nominal {sp['nominal'] / 1e6:.3g} MHz)") if sp["kind"] == "toggle"
                                    else f"{k}: {sp['lo']:.3f}–{sp['hi']:.3f} V across PVT (nominal {sp['nominal']:.3f} V)")
                    n_fail = len(an.get("failed", []))
                    lv.stage("pvt", "done", f"{45 - n_fail} / 45 simulated · {len(an['findings'])} finding(s)")
            elif not tbr.get("ok"):
                lv.stage("nominal", "error", tbr.get("error", ""))
                lv.stage("pvt", "skipped")
                store.event(rid, "nominal", f"The operating point did not run: {tbr.get('error')}"
                            + (f" {tbr['include_note']}" if tbr.get("include_note") else ""), "error")
            else:
                nom = tbr["nominal"]
                sat = {k for k, v in nom.items() if v["region"] == "sat"}
                devs = {}
                for k, v in nom.items():
                    name = map_device(k, inst)
                    if name:
                        e = devs.setdefault(name, dict(nominal=v["region"], margin=None, worst=None, members=0))
                        e["members"] += 1
                lv.set(devices=devs)
                lv.stage("nominal", "done", f"{len(nom)} transistors · {len(sat)} saturated")
                store.event(rid, "nominal", f"{len(nom)} transistors at tt, 27 °C, nominal supply; {len(sat)} in "
                                            f"saturation")

                lv.stage("pvt", "running", "0 / 45")
                done = [0]

                def on_result(c, ops, err):
                    cell = dict(corner=c[0], temp=c[1], vscale=c[2])
                    if err or not ops:
                        cell.update(status="err", note=err or "no result")
                    else:
                        bad = [k for k in sat if k in ops and ops[k]["region"] == "triode"]
                        worst = min((margin(ops[k]) for k in sat if k in ops), default=None)
                        cell.update(status="warn" if bad else "ok", n_triode=len(bad), worst_margin=worst,
                                    devices=sorted(bad)[:12])
                        with lv.lock:
                            for k in sat:
                                name = map_device(k, inst)
                                if k not in ops or not name or name not in lv.d["devices"]:
                                    continue
                                m, e = margin(ops[k]), lv.d["devices"][name]
                                if e["margin"] is None or m < e["margin"]:
                                    e["margin"], e["worst"] = m, list(c)
                    with lv.lock:
                        lv.d["cells"].append(cell)
                        done[0] += 1
                        lv.d["stages"]["pvt"]["note"] = f"{done[0]} / 45"
                        lv.save()

                on_result(NOMINAL, nom, None)
                conds = [[t, v] for t in TEMPS for v in VSCALES]

                def run_corner(k):
                    for r in engine.corner(ws, rel, k, conds, fixed):
                        if (k, r["temp"], r["vscale"]) != NOMINAL:
                            on_result((k, r["temp"], r["vscale"]), r["ops"], r["error"])

                threads = [threading.Thread(target=run_corner, args=(k,)) for k in CORNERS]
                for th in threads:
                    th.start()
                for th in threads:
                    th.join()
                an = engine.analyse(ws, rel)
                for f in an["findings"]:
                    store.add_finding(rid, dict(rule=f["rule"], severity=f["severity"], kind="risk",
                                                title=f["message"][:180], location=f"{rel} · {f['device']}",
                                                device=map_device(f["device"], inst) or "",
                                                detail=dict(f, corrected=bool(tbr.get("corrections")))))
                n_fail = len(an.get("failed", []))
                lv.stage("pvt", "done", f"{45 - n_fail} / 45 simulated · {len(an['findings'])} finding(s)")
                store.event(rid, "pvt", f"Swept 45 conditions ({45 - n_fail} simulated): {len(an['findings'])} "
                                        f"device(s) lose saturation or bias somewhere")

        if tbs:
            testbench_loops(rid, ws, tbs)

        # ---- Muse Spark: the tests the designer did not write --------------------------------------------------
        lv.stage("muse", "running")
        if not planner.configured("muse"):
            # without the model, every cell is still powered up (the no-model baseline), clearly labelled as such
            try:
                res = planner.review("rules", ws, project_docs(root), "")   # (the chip's supplies, for the rail guess)
                nf = keep_plans(rid, lv, res, "rules")
                lv.stage("muse", "done", f"no model · {len(res['plans'])} cell(s) powered up · {nf} finding(s)" + unc_note(lv))
                store.event(rid, "muse", f"Muse Spark is not connected on this server. As a baseline, every cell with "
                                         f"named supply and ground pins was powered up at 30 conditions "
                                         f"({len(res['plans'])} cell(s), {nf} finding(s)); the loops its testbenches close were "
                                         f"measured; any other loop needs the planner to choose where to cut.", "warn")
            except (planner.PlannerError, engine.EngineError) as e:
                lv.stage("muse", "skipped", "not connected")
                store.event(rid, "muse", f"Muse Spark is not connected; the baseline power-up did not run: {e}", "warn")
        else:
            try:
                plans = []

                def log(kind, text, **kw):
                    store.event(rid, "muse", text)
                    if kind == "plan" and kw.get("plan"):
                        plans.append(kw["plan"])
                        lv.set(plans=plans)

                res = planner.review("muse", ws, project_docs(root), floor_note(tbs, locals().get("tbr")), log)
                nf = keep_plans(rid, lv, res, "muse")
                lv.set(blocks=res["blocks"])
                lv.stage("muse", "done", f"{len(res['blocks'])} blocks · {len(res['plans'])} test(s) · {nf} finding(s)" + unc_note(lv))
            except (planner.PlannerError, engine.EngineError) as e:
                lv.stage("muse", "error", "planner failed")
                store.event(rid, "muse", f"Muse Spark review did not complete: {e}", "error")

        try:                                  # the same tests on the layout as drawn, with its capacitance
            post_layout(rid, lv, root, files, lay)
        except (engine.EngineError, OSError) as e:
            store.event(rid, "muse", f"The post-layout comparison did not complete: {e}", "warn")

        lv.stage("review", "running")
        n = len(store.findings(rid))
        summary = dict(findings=n, units=n_units, seconds=round(time.time() - t0, 1))
        lv.stage("review", "done", f"{n} finding(s)")
        store.event(rid, "review", f"Review finished in {summary['seconds']} s with {n} finding(s)")
        store.update_run(rid, status="done", stage="done", finished=time.time(), summary=summary)
    except Exception as e:
        store.event(rid, "error", str(e), "error")
        with lv.lock:
            for s, st in lv.d["stages"].items():
                if st["state"] == "running":
                    st["state"] = "error"
            lv.save()
        store.update_run(rid, status="error", finished=time.time())


def try_fix(rid, fid):
    """A sizing fix for one headroom finding: Muse Spark proposes sizes, the engine proves them at all 45 conditions
    (app/sizing.py); the outcome is attached to the finding."""
    f = store.finding(rid, fid)
    lv = store.live(rid)
    if not f or not lv.get("ws") or not f["rule"].startswith("analog/headroom"):
        return
    store.update_finding(rid, fid, fix={"state": "running"})
    try:
        r = sizing.fix(design_files(os.path.join(WORK, rid)), lv["testbench"], dict(f["detail"], title=f["title"]),
                       bool(lv.get("corrected")), log=lambda msg, level="info": store.event(rid, "fix", msg, level))
        store.update_finding(rid, fid, fix=dict(r, state="done"))
    except Exception as e:
        store.update_finding(rid, fid, fix={"state": "error", "why": str(e)})


# a hosted Kaaval shares one machine: at most this many reviews simulate at once, the rest wait their turn
_SLOTS = threading.BoundedSemaphore(int(os.environ.get("KAAVAL_MAX_REVIEWS", "2")))


_WAITING = [0]


def waiting():
    """Reviews queued for a simulation slot right now."""
    return _WAITING[0]


def _queued(rid, src, root):
    if not _SLOTS.acquire(blocking=False):
        _WAITING[0] += 1
        store.event(rid, "fetch", "Waiting for a free simulation slot (other reviews are running on this server)")
        _SLOTS.acquire()
        _WAITING[0] -= 1
    try:
        review(rid, src, root)
    finally:
        _SLOTS.release()


def adopt(rid, root):
    """Move an unpacked upload (an `upload-*` folder in WORK, or the one project folder inside it) to WORK/<rid>, so
    the run's folder is the project root, as it is for a cloned repository; returns it. Anything else stays put."""
    work = os.path.realpath(WORK)
    real = os.path.realpath(root)
    rel = os.path.relpath(real, work)
    top = rel.split(os.sep)[0]
    if rel.startswith("..") or not top.startswith("upload-"):
        return root
    dest = os.path.join(work, rid)
    if os.path.exists(dest):
        return root
    os.rename(real, dest)                      # the project folder itself (a zip's one top folder is dropped)
    if real != os.path.join(work, top):
        shutil.rmtree(os.path.join(work, top), ignore_errors=True)
    return dest


def start(src, root=None):
    rid = store.new_run(src.describe())
    if root:                                   # an upload: its files move to the run's own folder, where the sheets,
        root = adopt(rid, root)                # chip view and Layout 3D read them
    threading.Thread(target=_queued, args=(rid, src, root), daemon=True).start()
    return rid

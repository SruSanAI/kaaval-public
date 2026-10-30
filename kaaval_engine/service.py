"""service.py — Kaaval's review engine as a local service (in-process; no network, no key).

The bench calls these routes exactly as it would call a remote engine, through Flask's test client (app/engine.py).
Everything that judges circuits is here and open: the text-only xschem netlister, the per-corner PVT simulator with
trimmed sky130 libraries, the units audit, the operating-point checks, power-up and loop-stability test plans,
SPICE-subcircuit cells and waveforms. The one thing not here is the sizing-fix search, which runs on Minnal's private
engine when one is connected (app/engine.py: fix).

    POST /v1/kaaval/workspace    {files: {path: text}}                  -> {ws}     design files, text only, capped
    POST /v1/kaaval/audit        {ws, scope?, tiles?}                   -> units / plausibility findings
    POST /v1/kaaval/testbenches  {ws, scope?, focus?}                   -> testbench schematics, best first
    POST /v1/kaaval/testbench    {ws, tb}                               -> DUT, circuit kind (static / dynamic), nominal op
    POST /v1/kaaval/corner       {ws, tb, corner, conds:[[temp, vscale]]} -> per-condition op summaries (cached)
    POST /v1/kaaval/analyse      {ws, tb}                               -> headroom + bias findings from the sweep
    POST /v1/kaaval/tcorner      {ws, tb, corner, conds}                -> switching circuits: per-output transient
    POST /v1/kaaval/tanalyse     {ws, tb}                               -> stops-switching / level-spread findings
    POST /v1/kaaval/startup      {ws, tb, corner, vscale?, temps?}      -> power-up from 0 V at each temperature
    POST /v1/kaaval/sanalyse     {ws, tb}                               -> does-not-start / two-states / oscillates
    POST /v1/kaaval/cells        {ws, scope?}                           -> every circuit cell: ports, size, netlist text
    POST /v1/kaaval/plan         {ws, plan}                             -> validate + run a reviewer's test plan
    POST /v1/kaaval/wave         {ws, plan, corner, temp, vscale, case} -> one power-up waveform
    POST /v1/kaaval/health       {}                                     -> ngspice version, PDK installed

Nothing a client sends is executed: files are written as text and only read by our parsers; simulations run decks
the engine builds itself.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
import uuid

from flask import Blueprint, jsonify, request


from kaaval_engine import checks, plan as kplan, sim, spice_cells, units  # noqa: E402
from kaaval_engine import netlist as knet  # noqa: E402
from kaaval_engine.netlist import _find_sym, symbol  # noqa: E402
from kaaval_engine.xsch import _props, parse  # noqa: E402

bp = Blueprint("kaaval_api", __name__, url_prefix="/v1/kaaval")
WS = os.path.expanduser(os.environ.get("KAAVAL_WS", "~/.kaaval/ws"))
MAX_BYTES, MAX_FILES, TTL = 40_000_000, 20000, 6 * 3600
TEXT_EXT = (".sch", ".sym", ".spice", ".sp", ".cir", ".spi", ".net", ".lib", ".yaml", ".yml", ".md", ".mag", "xschemrc")
_SWEEPS, _TSWEEPS, _SUSWEEPS, _LOCK = {}, {}, {}, threading.Lock()


_SEM = threading.BoundedSemaphore(int(os.environ.get("KAAVAL_SIMS", "2")))       # simulations at once


def _gc():
    now = time.time()
    if os.path.isdir(WS):
        for d in os.listdir(WS):
            p = os.path.join(WS, d)
            if now - os.path.getmtime(p) > TTL:
                shutil.rmtree(p, ignore_errors=True)


def _ws(d):
    ws = str(d.get("ws") or "")
    if not re.fullmatch(r"[0-9a-f]{16}", ws) or not os.path.isdir(os.path.join(WS, ws)):
        return None
    return os.path.join(WS, ws)


def _inside(root, rel):
    p = os.path.realpath(os.path.join(root, rel or ""))
    return p if p == os.path.realpath(root) or p.startswith(os.path.realpath(root) + os.sep) else None


def _bad(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


@bp.post("/workspace")
def workspace():
    files = (request.get_json(silent=True) or {}).get("files") or {}
    if not isinstance(files, dict) or not files:
        return _bad("files {path: text} is required")
    if len(files) > MAX_FILES or sum(len(v or "") for v in files.values()) > MAX_BYTES:
        return _bad("design too large")
    _gc()
    ws = uuid.uuid4().hex[:16]
    root = os.path.join(WS, ws)
    os.makedirs(root)
    for rel, text in files.items():
        if not isinstance(text, str) or not rel.endswith(TEXT_EXT) or rel.startswith("/") or ".." in rel.split("/"):
            continue
        p = _inside(root, rel)
        if not p:
            continue
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)
    return jsonify({"ok": True, "ws": ws})


@bp.post("/audit")
def audit():
    d = request.get_json(silent=True) or {}
    root = _ws(d)
    scope = root and _inside(root, d.get("scope", ""))
    if not scope:
        return _bad("unknown workspace or scope", 404)
    a = units.audit_repo(scope, d.get("tiles") or "1x2")
    for x in a["findings"]:
        x["file"] = os.path.relpath(os.path.join(scope, x["file"]), root) if not os.path.isabs(x["file"]) else x["file"]
    return jsonify(dict(ok=True, netlists=a["netlists"], devices=a["devices"], chip_um2=a["chip_um2"],
                        findings=a["findings"]))


@bp.post("/testbenches")
def testbenches():
    d = request.get_json(silent=True) or {}
    root = _ws(d)
    scope = root and _inside(root, d.get("scope", ""))
    if not scope:
        return _bad("unknown workspace or scope", 404)
    out = []
    for dd, dirs, fs in os.walk(scope):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in fs:
            if f.endswith(".sch"):
                t = open(os.path.join(dd, f), errors="replace").read()
                # a testbench drives the circuit with sources; it has no ports, or it carries simulator commands
                if re.search(r"^C \{devices/(vsource|isource)\.sym\}", t, re.M) and (
                        not re.search(r"^C \{devices/(ipin|opin|iopin)\.sym\}", t, re.M)
                        or re.search(r"^C \{devices/(code|code_shown|simulator_commands[\w]*)\.sym\}", t, re.M)):
                    out.append(os.path.relpath(os.path.join(dd, f), root))
    focus = d.get("focus") or ""
    kinds = {}
    for rel in out:
        try:
            kinds[rel] = checks.circuit_kind(sim.Testbench.from_sch(os.path.join(root, rel)))["kind"]
        except Exception:
            kinds[rel] = "unknown"
    # the file the user pointed at first; then bias-point testbenches (every check applies), then the rest
    out.sort(key=lambda p: (0 if focus and p.endswith(focus) else 1, 0 if kinds[p] == "static" else 1,
                            0 if re.search(r"(^|/)(tb|test)", os.path.basename(p), re.I) else 1, p))
    return jsonify({"ok": True, "testbenches": out, "kinds": kinds})


def _dut_of(tb_sch):
    best = None
    local = os.path.dirname(tb_sch)
    for kind, f, props in parse(open(tb_sch, errors="replace").read()):
        if kind != "C":
            continue
        path = _find_sym(f[0], local)
        if not path or symbol(path)["type"] != "subcircuit":
            continue
        sch = os.path.splitext(path)[0] + ".sch"
        if os.path.exists(sch):
            n = open(sch, errors="replace").read().count("\nC {")
            if not best or n > best[2]:
                best = (_props(props).get("name", "x1"), sch, n)
    return (best[0], best[1]) if best else (None, None)


def _tb(d):
    root = _ws(d)
    p = root and _inside(root, d.get("tb", ""))
    return (root, p) if p and os.path.isfile(p) else (root, None)


def _testbench(d, p):
    """The testbench as written, or with its units traps corrected when the client asks (fix_traps)."""
    tb = sim.Testbench.from_sch(p)
    if d.get("fix_traps"):
        circ, changes = units.correct_circuit(tb.circuit)
        tb = sim.Testbench(sch=tb.sch, circuit=circ, analyses=tb.analyses, params=tb.params, options=tb.options)
        return tb, changes
    return tb, []


def _compact(ops):
    return {k: {"region": v["region"], "id": v.get("id"), "vds": v.get("vds"), "vdsat": v.get("vdsat")}
            for k, v in (ops or {}).items()}


@bp.post("/testbench")
def testbench():
    d = request.get_json(silent=True) or {}
    root, p = _tb(d)
    if not p:
        return _bad("unknown testbench", 404)
    inst, dut = _dut_of(p)
    tb, changes = _testbench(d, p)
    kind = dict(checks.circuit_kind(tb), corrections=changes)
    if kind["kind"] == "dynamic":
        nets, win = sim.output_nets(tb), sim.tran_window(tb)
        return jsonify({"ok": True, "dut_inst": inst, "dut": dut and os.path.relpath(dut, root), "nominal": {},
                        "outputs": nets, "window": win, **kind})
    with _SEM:
        ops, err = sim.op_points(tb, *checks.NOMINAL)
    if err or not ops:
        return jsonify({"ok": False, "error": err or "no transistors", "dut_inst": inst,
                        "dut": dut and os.path.relpath(dut, root)})
    with _LOCK:
        _SWEEPS[(root, p)] = {checks.NOMINAL: (ops, None)}
    return jsonify({"ok": True, "dut_inst": inst, "dut": dut and os.path.relpath(dut, root),
                    "nominal": _compact(ops), **kind})


@bp.post("/corner")
def corner():
    d = request.get_json(silent=True) or {}
    root, p = _tb(d)
    if not p or d.get("corner") not in checks.CORNERS:
        return _bad("unknown testbench or corner", 404)
    conds = [(int(t), float(v)) for t, v in d.get("conds") or []]
    with _SEM:
        res = sim.op_points_corner(_testbench(d, p)[0], d["corner"], conds)
    with _LOCK:
        sw = _SWEEPS.setdefault((root, p), {})
        for (t, v), r in res.items():
            sw[(d["corner"], t, v)] = r
    return jsonify({"ok": True, "results": [{"temp": t, "vscale": v, "error": e, "ops": _compact(ops)}
                                            for (t, v), (ops, e) in res.items()]})


@bp.post("/tcorner")
def tcorner():
    """The designer's transient at each condition of one corner (switching circuits): per output mean / swing / freq."""
    d = request.get_json(silent=True) or {}
    root, p = _tb(d)
    if not p or d.get("corner") not in checks.CORNERS:
        return _bad("unknown testbench or corner", 404)
    tb = _testbench(d, p)[0]
    nets, win = sim.output_nets(tb), sim.tran_window(tb)
    if not nets or not win:
        return _bad("no outputs or no transient analysis to run", 422)
    conds = [(int(t), float(v)) for t, v in d.get("conds") or []]
    with _SEM:
        res = sim.tran_corner(tb, d["corner"], conds, nets, win)
    with _LOCK:
        sw = _TSWEEPS.setdefault((root, p), {})
        for (t, v), r in res.items():
            sw[(d["corner"], t, v)] = r
    return jsonify({"ok": True, "results": [{"temp": t, "vscale": v, "error": e, "outputs": m}
                                            for (t, v), (m, e) in res.items()]})


@bp.post("/tanalyse")
def tanalyse():
    d = request.get_json(silent=True) or {}
    root, p = _tb(d)
    sw = _TSWEEPS.get((root, p))
    if not sw or checks.NOMINAL not in sw:
        return _bad("run /tcorner for every corner first", 409)
    fs, spread = checks.function_loss(sw)
    return jsonify({"ok": True, "findings": fs, "spread": spread,
                    "failed": [list(c) for c, (o, e) in sw.items() if e]})


@bp.post("/startup")
def startup():
    """Power-up from 0 V at each temperature of one corner and supply scale (static circuits)."""
    d = request.get_json(silent=True) or {}
    root, p = _tb(d)
    if not p or d.get("corner") not in checks.CORNERS:
        return _bad("unknown testbench or corner", 404)
    vs = float(d.get("vscale", 1.0))
    temps = [int(t) for t in d.get("temps") or checks.SU_TEMPS]
    with _SEM:
        res = sim.startup_checked(_testbench(d, p)[0], d["corner"], temps, vs, ramp=20e-6, settle=200e-6)
    with _LOCK:
        sw = _SUSWEEPS.setdefault((root, p), {})
        for t, r in res.items():
            sw[(d["corner"], t, vs)] = r
    return jsonify({"ok": True, "results": [{"temp": t, "vscale": vs, "error": e, "result": r}
                                            for t, (r, e) in res.items()]})


@bp.post("/sanalyse")
def sanalyse():
    d = request.get_json(silent=True) or {}
    root, p = _tb(d)
    sw = _SUSWEEPS.get((root, p))
    if not sw:
        return _bad("run /startup first", 409)
    return jsonify({"ok": True, "findings": checks.startup(sw),
                    "failed": [list(c) + [e] for c, (r, e) in sw.items() if e]})


@bp.post("/cells")
def cells():
    """Every circuit cell (a schematic with ports) in the workspace, for a planner to read: its ports, how many
    devices it holds, and its netlist as our netlister writes it (capped), so the planner sees the circuit, not
    pictures. Testbenches (no ports) are listed by /testbenches."""
    d = request.get_json(silent=True) or {}
    root = _ws(d)
    scope = root and _inside(root, d.get("scope", ""))
    if not scope:
        return _bad("unknown workspace or scope", 404)
    out = []
    for dd, dirs, fs in os.walk(scope):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in sorted(fs):
            if not f.endswith(".sch"):
                continue
            p = os.path.join(dd, f)
            t = open(p, errors="replace").read()
            ports = re.findall(r"^C \{devices/(?:ipin|opin|iopin)\.sym\}[^{]*\{[^}]*?lab=([^\s}]+)", t, re.M)
            if not ports:
                continue
            try:
                net = knet.netlist(p)
            except Exception as e:                      # noqa: BLE001 - reported, not fatal
                net = f"* could not netlist: {e}"
            devs = sum(1 for l in net.splitlines() if l[:1].lower() in "xmqrcd" and not l.startswith(".") )
            out.append(dict(cell=os.path.relpath(p, root), ports=ports, devices=devs, netlist=net[:12000]))
            if len(out) >= 60:
                break
    # repositories without schematics: SPICE subcircuits are cells too ("<file>#<NAME>", sanitised to definitions)
    if len(out) < 60:
        for c in spice_cells.find_cells(scope, 60 - len(out)):
            f, _, name = c["cell"].partition("#")
            c["cell"] = os.path.relpath(os.path.join(scope, f), root) + "#" + name   # plans resolve from the root
            out.append(c)
    return jsonify({"ok": True, "cells": out})


@bp.post("/health")
def health():
    return jsonify(dict(sim.health(), ok=True))


@bp.post("/wave")
def wave():
    d = request.get_json(silent=True) or {}
    root = _ws(d)
    pl = d.get("plan")
    if not root or not isinstance(pl, dict) or d.get("corner") not in checks.CORNERS:
        return _bad("unknown workspace, plan or corner", 404)
    with _SEM:
        r, e = kplan.wave(pl, root, d["corner"], d.get("temp", 27), d.get("vscale", 1.0), d.get("case"))
    return jsonify({"ok": not e, "error": e, "wave": r})


@bp.post("/deck")
def deck():
    d = request.get_json(silent=True) or {}
    root = _ws(d)
    pl = d.get("plan")
    if not root or not isinstance(pl, dict) or d.get("corner") not in checks.CORNERS:
        return _bad("unknown workspace, plan or corner", 404)
    text, e = kplan.bench_deck(pl, root, d["corner"], d.get("temp", 27), d.get("vscale", 1.0), d.get("case"))
    return jsonify({"ok": not e, "error": e, "deck": text})


@bp.post("/plan")
def run_plan():
    """Validate and run one test plan (kaaval_engine.plan): data only, compiled by us. A rejected plan returns its
    errors, so a planner can correct it."""
    d = request.get_json(silent=True) or {}
    root = _ws(d)
    pl = d.get("plan")
    if not root or not isinstance(pl, dict):
        return _bad("unknown workspace or missing plan", 404)
    errs = kplan.validate(pl, root)
    if errs:
        return jsonify({"ok": False, "errors": errs}), 422
    with _SEM:
        r = kplan.run(pl, root)
    return jsonify(r)


@bp.post("/analyse")
def analyse():
    d = request.get_json(silent=True) or {}
    root, p = _tb(d)
    sw = _SWEEPS.get((root, p))
    if not sw or checks.NOMINAL not in sw:
        return _bad("run /testbench and /corner first", 409)
    return jsonify({"ok": True, "findings": checks.headroom(sw) + checks.bias(sw),
                    "failed": [list(c) for c, (o, e) in sw.items() if e]})


"""server.py — the Kaaval web app: give it a design (any repository link or a .zip), watch the review on the bench.

    python -m app.server            (then open http://127.0.0.1:5110; KAAVAL_PORT changes the port)
"""
import hmac, io, json, os, re, tempfile, threading, time, uuid, zipfile

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from guard import sch_svg
from kaaval_engine import chip as kchip
from app import engine, inputs, planner, runner, store

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024


def _page(name):
    """A page whose /static/ links carry each file's modification time (?v=), so a cache in front of Kaaval (a CDN,
    a browser) always fetches the new file after an update; the page itself is never cached."""
    html = open(os.path.join(STATIC, name), encoding="utf-8").read()

    def stamp(m):
        f = os.path.join(STATIC, m.group(1))
        return f'/static/{m.group(1)}?v={int(os.path.getmtime(f))}' if os.path.isfile(f) else m.group(0)
    r = app.response_class(re.sub(r"/static/([\w.\-/]+\.(?:js|css|json))", stamp, html), mimetype="text/html")
    r.headers["Cache-Control"] = "no-cache"
    return r


@app.get("/")
def home():
    return _page("index.html")


@app.get("/runs/<rid>")
def bench(rid):
    if not store.run(rid):
        abort(404)
    return _page("bench.html")


@app.get("/static/<path:p>")
def static_files(p):
    r = send_from_directory(STATIC, p)
    # versioned links (?v=) can be cached for a long time; anything fetched without one must be revalidated
    r.headers["Cache-Control"] = "public, max-age=31536000, immutable" if request.args.get("v") else "no-cache"
    return r


@app.get("/api/status")
def api_status():
    """The local engine's simulator and PDK, and whether Muse Spark is connected. No key ever reaches the browser."""
    sim = engine.health()
    return jsonify(ok=True, why="local engine", ngspice=sim.get("ngspice"), pdk=sim.get("pdk"), sim_ok=bool(sim.get("ok")),
                   muse=planner.configured("muse"))


@app.post("/api/parse")
def api_parse():
    """Live feedback while the user types: what we understood."""
    try:
        s = inputs.parse((request.get_json(silent=True) or {}).get("text", ""))
        return jsonify(ok=True, kind=s.kind, label=s.label, ref=s.ref, path=s.path, focus=s.focus)
    except ValueError as e:
        return jsonify(ok=False, error=str(e))


# a public Kaaval runs on someone's machine: who may start a review, how often, and how long the queue may grow
ACCESS = os.environ.get("KAAVAL_ACCESS_CODE", "")
PER_HOUR = int(os.environ.get("KAAVAL_REVIEWS_PER_HOUR", "4"))
MAX_WAITING = int(os.environ.get("KAAVAL_MAX_WAITING", "6"))
_starts, _starts_lock = {}, threading.Lock()


def _gate():
    """None when this request may start a review, else (message, status)."""
    if ACCESS:
        code = request.headers.get("X-Kaaval-Code") or request.form.get("code") or \
            (request.get_json(silent=True) or {}).get("code", "")
        if not hmac.compare_digest(str(code), ACCESS):
            return "This Kaaval needs an access code to start a review.", 403
    if runner.waiting() >= MAX_WAITING:
        return "Kaaval is busy with other reviews right now; try again in a few minutes.", 429
    ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"
    now = time.time()
    with _starts_lock:
        recent = [t for t in _starts.get(ip, []) if now - t < 3600]
        if len(recent) >= PER_HOUR:
            return f"At most {PER_HOUR} reviews per hour from one address; try again later.", 429
        _starts[ip] = recent + [now]
    return None


@app.get("/api/access")
def api_access():
    return jsonify(code_required=bool(ACCESS))


@app.post("/api/runs")
def api_new_run():
    g = _gate()
    if g:
        return jsonify(error=g[0], need_code=g[1] == 403), g[1]
    if "file" in request.files:
        f = request.files["file"]
        if not f.filename.lower().endswith(".zip"):
            return jsonify(error="Drop a .zip of the project folder."), 400
        rid_dir = os.path.join(runner.WORK, "upload-" + uuid.uuid4().hex[:8])
        os.makedirs(rid_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as t:
            f.save(t.name)
        try:
            root = inputs.unpack_zip(t.name, rid_dir)
        except Exception as e:
            return jsonify(error=f"Could not open the zip: {e}"), 400
        finally:
            os.unlink(t.name)
        src = inputs.Source("zip", label=f.filename)
        return jsonify(id=runner.start(src, root=root))
    try:
        src = inputs.parse((request.get_json(silent=True) or {}).get("text", ""))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(id=runner.start(src))


@app.get("/api/runs")
def api_runs():
    """Only the runs this browser started (it sends their ids): a public Kaaval never lists other visitors' reviews."""
    ids = [i for i in request.args.get("ids", "").split(",") if re.fullmatch(r"[0-9a-f]{10}", i)][:20]
    return jsonify([r for r in (store.run(i) for i in ids) if r])


@app.get("/api/runs/<rid>")
def api_run(rid):
    r = store.run(rid)
    if not r:
        abort(404)
    after = float(request.args.get("after", 0))
    lv = store.live(rid)
    if request.args.get("svg") != "1":
        lv.pop("svg", None)
    return jsonify(run=r, events=store.events(rid, after), findings=store.findings(rid), live=lv,
                   stage_names=runner.STAGE_NAMES, stages=runner.STAGES)


@app.get("/api/runs/<rid>/sheet")
def api_sheet(rid):
    """A sub-sheet of the reviewed circuit, for devices that live below the top schematic: path is the chain of
    instance names under the circuit (x1.x2), hl the device to mark on that sheet."""
    lv = store.live(rid)
    if not lv:
        abort(404)
    root = os.path.realpath(os.path.join(runner.WORK, rid))
    # a planned test names its own cell (a schematic in the repository); otherwise the reviewed circuit's sheet
    cell = request.args.get("cell", "")
    if cell:
        cur = os.path.realpath(os.path.join(root, cell))
        if not cur.startswith(root + os.sep) or not cur.endswith(".sch") or not os.path.isfile(cur):
            return jsonify(ok=False, error="no such schematic"), 404
    elif lv.get("dut"):
        cur = os.path.realpath(os.path.join(root, lv["dut"]))
    else:
        abort(404)
    names = [cur]
    for inst in [x for x in request.args.get("path", "").split(".") if x]:
        nxt = sch_svg.child_sheet(cur, inst)
        if not nxt or not os.path.realpath(nxt).startswith(root + os.sep):
            return jsonify(ok=False, error=f"no schematic behind {inst}"), 404
        cur = os.path.realpath(nxt)
        names.append(cur)
    hl = request.args.get("hl", "")
    return jsonify(ok=True, svg=sch_svg.render(cur, highlight=(hl,) if hl else ()),
                   sheets=[os.path.relpath(n, root) for n in names])


ASK_LIMIT = int(os.environ.get("KAAVAL_ASK_LIMIT", "20"))      # questions per review (each one is a model call)


def review_text(rid, lv):
    """A finished review as the question-answering model reads it: what was reviewed, the tests, the blocks named and
    every finding with its id and measured numbers (capped)."""
    r, fs = store.run(rid) or {}, store.findings(rid)
    out = [f"Repository: {lv.get('source') or r.get('repo')} (commit {(r.get('commit_sha') or '')[:7]})",
           f"Circuit simulated by the designer's testbench: {lv.get('dut') or '-'} via {lv.get('testbench') or '-'}"]
    for s, st in (lv.get("stages") or {}).items():
        if st.get("note"):
            out.append(f"Stage {s}: {st['note']}")
    for b in lv.get("blocks") or []:
        out.append(f"Block {b.get('cell')}: {b.get('function')} (risks: {', '.join(b.get('risks') or []) or '-'})")
    for pr in lv.get("plan_results") or []:
        p = pr.get("plan") or {}
        out.append(f"Test run: {p.get('kind')} on {p.get('cell')} ({len(pr.get('results') or [])} conditions)"
                   + (f" - why: {p.get('why')}" if p.get("why") else ""))
    out.append(f"Findings ({len(fs)}):")
    for f in fs:
        d = f.get("detail") or {}
        nums = {k: d[k] for k in ("worst", "n_bad", "n", "nominal_id", "worst_id", "nominal_margin", "worst_margin",
                                  "margins", "loop", "floating", "held") if k in d}
        if isinstance(nums.get("margins"), dict):
            nums["margins"] = {k: nums["margins"].get(k) for k in ("pm", "gm_db", "ugf", "dc_gain_db")}
        out.append(f"- id {f.get('id')}: {f['rule']} ({f.get('kind')}, {f.get('severity')}) at {f.get('location')}: "
                   f"{(f.get('title') or '')[:700]} | {json.dumps(nums, default=str)[:600]}")
    return dict(text="\n".join(out)[:60000], ids=[str(f.get("id")) for f in fs])


ASK_PER_HOUR = int(os.environ.get("KAAVAL_ASKS_PER_HOUR", "30"))
_asks, _asked = {}, {}


def _ask_gate():
    """None when this request may ask Muse Spark a question, else (message, status): the access code a review needs,
    and at most ASK_PER_HOUR questions an hour from one address."""
    if ACCESS:
        code = request.headers.get("X-Kaaval-Code") or (request.get_json(silent=True) or {}).get("code", "")
        if not hmac.compare_digest(str(code), ACCESS):
            return "This Kaaval needs its access code to ask Muse Spark.", 403
    ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"
    now = time.time()
    with _starts_lock:
        recent = [t for t in _asks.get(ip, []) if now - t < 3600]
        if len(recent) >= ASK_PER_HOUR:
            return f"At most {ASK_PER_HOUR} questions an hour from one address; try again later.", 429
        _asks[ip] = recent + [now]
    return None


@app.post("/api/runs/<rid>/ask")
def api_ask(rid):
    """A question about a finished review, answered by Muse Spark from the review's own findings and tests."""
    lv = store.live(rid)
    if lv is None or not store.run(rid):
        abort(404)
    if not planner.configured("muse"):
        return jsonify(ok=False, error="Muse Spark is not connected on this server"), 503
    g = _ask_gate()                                    # each question is a paid model call: same code as a review
    if g:
        return jsonify(ok=False, error=g[0]), g[1]
    running = (store.run(rid) or {}).get("status") not in ("done", "error")
    q = str((request.get_json(silent=True) or {}).get("q", "")).strip()
    if not q or len(q) > 1000:
        return jsonify(ok=False, error="ask a question of up to 1000 characters"), 400
    with _starts_lock:                                 # counted here, never in the run's live record (the runner owns it)
        asked = _asked.get(rid, 0)
        if asked >= ASK_LIMIT:
            return jsonify(ok=False, error=f"this review has had its {ASK_LIMIT} questions"), 429
        _asked[rid] = asked + 1
    rv = review_text(rid, lv)
    if running:
        rv = dict(rv, text="THE REVIEW IS STILL RUNNING: answer from what it has so far and say so.\n" + rv["text"])
    try:
        a = planner.ask(q, rv)
    except planner.PlannerError as e:
        return jsonify(ok=False, error=str(e)), 502
    store.event(rid, "muse", f"Asked: {q[:200]}")
    return jsonify(ok=True, answer=a["answer"], cites=a["cites"])


@app.get("/runs/<rid>/layout3d")
def layout3d_page(rid):
    if not store.run(rid):
        abort(404)
    return _page("layout3d.html")


@app.get("/api/runs/<rid>/layout3d")
def api_layout3d(rid):
    """A cell's committed Magic layout of this run's repository as stacked 3D layers (kaaval_engine.layout3d)."""
    if not store.run(rid):
        abort(404)
    from kaaval_engine import layout3d
    root = os.path.realpath(os.path.join(runner.WORK, rid))
    mag = request.args.get("mag", "")
    if not mag:                                    # no cell named: the layouts of this repository, to choose from
        out = []
        for d, ds, fs in os.walk(root):
            ds[:] = [x for x in ds if not x.startswith(".")]
            out += [os.path.relpath(os.path.join(d, f), root) for f in fs if f.endswith(".mag")]
        try:                                       # the project's top cell (its top module), to open first
            top = kchip.read(root).get("top") or ""
        except Exception:                          # noqa: BLE001 - no top module: no default
            top = ""
        from kaaval_engine import layout_check as LC     # cells drawn both ways: the analog blocks, to open first
        analog = [p["mag"] for p in LC.pairs(root)]
        return jsonify(ok=True, mags=sorted(out)[:400], top=top, analog=analog)
    try:
        return jsonify(ok=True, **layout3d.read(root, mag))
    except (ValueError, OSError) as e:
        return jsonify(ok=False, error=str(e)), 404


@app.get("/runs/<rid>/chip")
def chip_page(rid):
    if not store.run(rid):
        abort(404)
    return _page("chip.html")


@app.get("/api/runs/<rid>/chip")
def api_chip(rid):
    """The whole Tiny Tapeout tile of the reviewed project (kaaval_engine.chip, read as text), with each analog
    block's tests and findings from this review attached, for the zoom view: chip -> block -> transistor."""
    lv = store.live(rid)
    if lv is None:
        abort(404)
    root = os.path.realpath(os.path.join(runner.WORK, rid))
    tile = kchip.read(root)
    plans = lv.get("plan_results") or []
    fs = store.findings(rid)
    mags = {}                                          # each block's committed layout, for the 3D view
    for d, ds, fns in os.walk(root):
        ds[:] = [x for x in ds if not x.startswith(".")]
        for f in fns:
            if f.endswith(".mag"):
                mags.setdefault(f[:-4].lower(), os.path.relpath(os.path.join(d, f), root))
    for inst in tile["instances"]:
        cell = (inst.get("cell") or "").lower()
        inst["mag"] = mags.get(os.path.splitext(os.path.basename(cell))[0]) or mags.get(inst.get("type", "").lower())
        mine = [(k, pr) for k, pr in enumerate(plans) if (pr.get("plan") or {}).get("cell", "").lower() == cell]
        inst["tests"] = [dict(k=k, kind=pr["plan"].get("kind"), why=pr["plan"].get("why"),
                              findings=[dict(rule=f["rule"], message=f["message"]) for f in
                                        ((pr.get("result") or {}).get("findings") or [])])
                         for k, pr in mine]
        # every stored finding of this block, with its id: the same finding the bench shows and walks through
        inst["findings"] = [dict(id=f["id"], rule=f["rule"], kind=f.get("kind"), severity=f.get("severity"),
                                 title=f.get("title", "")[:400]) for f in fs if _belongs(f, cell, lv)]
    return jsonify(ok=True, **tile)


def _belongs(f, cell, lv):
    """Does a stored finding belong to the chip block drawn from `cell` (a schematic path, lower case)? A planned
    test's cell; a testbench loop's cut subcircuit (by the schematic's name); a layout comparison's schematic;
    otherwise the circuit the review simulated. A units trap belongs to no block."""
    if not cell:
        return False
    d = f.get("detail") or {}
    if (d.get("plan") or {}).get("cell"):
        return d["plan"]["cell"].lower() == cell
    if d.get("loop"):
        return os.path.splitext(os.path.basename(cell))[0] == (d["loop"].get("subckt") or "").lower()
    if f["rule"].startswith("layout/"):
        return (d.get("sch") or "").lower() == cell
    return f.get("kind") != "trap" and (lv.get("dut") or "").lower() == cell


@app.get("/api/runs/<rid>/wave")
def api_wave(rid):
    """One power-up waveform for a planned test at one condition (the bench's evidence view)."""
    lv = store.live(rid)
    plans = (lv or {}).get("plan_results") or []
    try:
        k = int(request.args.get("k", -1))
        pr = plans[k]
    except (ValueError, IndexError):
        abort(404)
    if pr["plan"].get("kind") not in ("powerup", "sequence"):
        return jsonify(ok=False, error="waveforms are for power-up tests"), 400
    try:
        r = engine.wave(lv["ws"], pr["plan"], request.args.get("corner", "tt"), int(request.args.get("temp", 27)),
                        float(request.args.get("vscale", 1.0)), request.args.get("case"))
    except engine.EngineError as e:
        return jsonify(ok=False, error=str(e)), 502
    return jsonify(r)


def _worst(w):
    """corner, temperature and supply scale from a finding's worst condition, whatever the test kind put around them."""
    w = list(w or [])
    c = next((x for x in w if x in ("tt", "ss", "ff", "sf", "fs")), "tt")
    rest = w[w.index(c) + 1:] if c in w else []
    nums = [x for x in rest if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return c, int(nums[0]) if nums else 27, float(nums[1]) if len(nums) > 1 else 1.0


@app.get("/api/runs/<rid>/findings/<fid>/evidence")
def api_evidence(rid, fid):
    """Everything behind one planned-test finding, as a zip anyone can check without Kaaval: the finding, the test
    plan, every condition the engine measured, and the testbench at the worst condition as a plain ngspice deck."""
    r, f, lv = store.run(rid), store.finding(rid, fid), store.live(rid) or {}
    det = (f or {}).get("detail") or {}
    if r and f and det.get("loop"):
        return _loop_evidence(rid, r, f, det, lv)
    plans = lv.get("plan_results") or []
    if not r or not f or not isinstance(det.get("k"), int) or det["k"] >= len(plans):
        abort(404)
    pr = plans[det["k"]]
    corner, temp, vscale = _worst(det.get("worst"))
    deck, derr = None, "the engine workspace is gone"
    for ws in (lv.get("ws"), "renew"):
        if ws == "renew":
            # the engine's workspaces expire; this run's copy of the repository is still on disk
            root = os.path.join(runner.WORK, rid)
            if not os.path.isdir(root):
                break
            ws = engine.upload(runner.design_files(root))
            store.set_live(rid, dict(lv, ws=ws))
        try:
            d = engine.deck(ws, pr["plan"], corner, temp, vscale, det.get("case"))
            deck, derr = d.get("deck"), d.get("error")
            break
        except engine.EngineError as e:
            deck, derr = None, str(e)
    info = dict(repository=r.get("repo"), commit=r.get("commit_sha"), finding=dict(rule=f["rule"],
                severity=f["severity"], message=det.get("message") or f.get("title"), worst=det.get("worst"),
                n_bad=det.get("n_bad"), n=det.get("n"), conds=det.get("conds")),
                planned_by=pr.get("by"), plan=pr["plan"], results=pr.get("results") or [],
                engine=engine.health(), deck=dict(corner=corner, temp=temp, vscale=vscale, error=derr))
    readme = (f"Kaaval evidence: {f['rule']}\n\n{info['finding']['message']}\n\n"
              f"finding.json  the finding, the test plan ({pr['plan'].get('kind')}) and all "
              f"{len(info['results'])} measured conditions\n"
              + (f"bench.sp      the testbench at {corner}, {temp} C, supply x{vscale:g}: the cell from your repository,\n"
                 f"              the plan's supplies, loads and stimuli, "
                 + ("then the DC answer and the same power-up from 0 V the engine ran\n"
                    "              (settled currents and nodes printed at the end, waveform in powerup.txt).\n"
                    if pr["plan"].get("kind") in ("powerup", "sequence") else "with an operating-point analysis.\n")
                 + f"              Set the .lib line to your sky130A install, then: ngspice -b bench.sp\n" if deck else
                 f"bench.sp      not included: {derr}\n")
              + "\nThe engine never edits your design: the deck adds sources and loads around your cell.\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", readme)
        z.writestr("finding.json", json.dumps(info, indent=1, default=str))
        if deck:
            z.writestr("bench.sp", deck)
    buf.seek(0)
    name = re.sub(r"[^a-z0-9]+", "_", f"kaaval_{f['rule']}_{rid}".lower())
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=name + ".zip")


def _loop_evidence(rid, r, f, det, lv):
    """A testbench-loop finding as a zip: the finding, the loop gain at every condition, and the loop-gain deck at the
    worst condition (the designer's testbench, cut where the engine cut it; ngspice prints the phase margin)."""
    corner, temp, vscale = _worst(det.get("worst"))
    deck, derr = None, "the engine workspace is gone"
    for ws in (lv.get("ws"), "renew"):
        if ws == "renew":
            root = os.path.join(runner.WORK, rid)
            if not os.path.isdir(root):
                break
            ws = engine.upload(runner.design_files(root))
            store.set_live(rid, dict(lv, ws=ws))
        try:
            d = engine.loop_deck(ws, det["testbench"], det["loop"], corner, temp, vscale)
            deck, derr = d.get("deck"), d.get("error")
            break
        except engine.EngineError as e:
            deck, derr = None, str(e)
    info = dict(repository=r.get("repo"), commit=r.get("commit_sha"), testbench=det.get("testbench"),
                loop=det["loop"], finding=dict(rule=f["rule"], severity=f["severity"], message=f.get("title"),
                                               worst=det.get("worst"), n_bad=det.get("n_bad"), n=det.get("n")),
                results=det.get("results") or [], engine=engine.health(),
                deck=dict(corner=corner, temp=temp, vscale=vscale, error=derr))
    readme = (f"Kaaval evidence: {f['rule']}\n\n{f.get('title')}\n\n"
              f"finding.json  the finding, the loop and its loop gain at all {len(info['results'])} conditions\n"
              + (f"loopgain.sp   your testbench {det.get('testbench')} at {corner}, {temp} C, supply x{vscale:g}, cut at "
                 f"{det['loop']['pin']}:\n              both injections of Tian's method; ngspice prints the unity-gain "
                 f"frequency and phase margin\n              and writes T(f) to loopgain.txt. Set the .lib line to your "
                 f"sky130A install, then: ngspice -b loopgain.sp\n" if deck else f"loopgain.sp   not included: {derr}\n")
              + "\nThe engine never edits your design: the deck cuts the loop with a 0 V source and adds the probes.\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", readme)
        z.writestr("finding.json", json.dumps(info, indent=1, default=str))
        if deck:
            z.writestr("loopgain.sp", deck)
    buf.seek(0)
    name = re.sub(r"[^a-z0-9]+", "_", f"kaaval_{f['rule']}_{rid}".lower())
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=name + ".zip")


@app.post("/api/runs/<rid>/findings/<fid>/fix")
def api_fix(rid, fid):
    import threading
    f = store.finding(rid, fid)
    if not f:
        abort(404)
    if (f.get("fix") or {}).get("state") == "running":
        return jsonify(ok=True)
    g = _ask_gate()                                    # a fix is several paid model calls: the same limits as a question
    if g:
        return jsonify(ok=False, error=g[0]), g[1]
    threading.Thread(target=runner.try_fix, args=(rid, fid), daemon=True).start()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("KAAVAL_PORT", 5110)), debug=False, threaded=True)

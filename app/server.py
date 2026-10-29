"""server.py — the Kaaval web app: give it a design (any repository link or a .zip), watch the review on the bench.

    python -m app.server            (then open http://127.0.0.1:5110; KAAVAL_PORT changes the port)
"""
import hmac, os, re, tempfile, threading, time, uuid

from flask import Flask, abort, jsonify, request, send_from_directory

from guard import sch_svg
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


@app.get("/api/minnal")
def api_minnal():
    """The local engine's simulator and PDK, Minnal's fix search (optional), and whether Muse Spark is connected.
    No key ever reaches the browser."""
    sim = engine.health()
    out = dict(ok=True, why="local engine", ngspice=sim.get("ngspice"), pdk=sim.get("pdk"), sim_ok=bool(sim.get("ok")),
               muse=planner.configured("muse"), minnal=False)
    url, key = os.environ.get("MINNAL_URL", ""), os.environ.get("MINNAL_KEY", "")
    if url and key:
        import urllib.request
        try:
            req = urllib.request.Request(url.rstrip("/") + "/v1/health", headers={"Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=3) as r:
                out["minnal"] = r.status == 200
        except Exception:
            pass
    return jsonify(out)


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


@app.post("/api/runs/<rid>/findings/<fid>/fix")
def api_fix(rid, fid):
    import threading
    f = store.finding(rid, fid)
    if not f:
        abort(404)
    if (f.get("fix") or {}).get("state") == "running":
        return jsonify(ok=True)
    threading.Thread(target=runner.try_fix, args=(rid, fid), daemon=True).start()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("KAAVAL_PORT", 5110)), debug=False, threaded=True)

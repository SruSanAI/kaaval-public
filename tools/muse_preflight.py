"""muse_preflight.py — is Muse Spark ready for Kaaval? One command, run the day the Meta key arrives.

    MUSE_API_KEY=... python tools/muse_preflight.py [--plan <local design folder>] [--image <schematic.png> --sch <same.sch>]

Checks, each printed as PASS / FAIL with its time:
  1. the key reaches the Meta Model API (Responses API, model muse-spark-1.3)
  2. JSON mode answers parse; strict json_schema is accepted (or the planner's JSON-mode fallback is used)
  3. image reading: a schematic image is uploaded (Files API, purpose user_data) and read; the transistor count Muse
     reports is compared with our own netlist of the same schematic (the ground truth)
  4. planning: Muse plans the review of a real design (blocks + test plans); every plan is validated by the engine,
     nothing is simulated (add --run to run them)
Nothing here is cached or shown in the app; the key is read from the environment only.
"""
import argparse, json, mimetypes, os, sys, time, urllib.error, urllib.request, uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import engine, planner, runner  # noqa: E402


def base():
    return (planner._env("MUSE_BASE_URL") or "https://api.meta.ai/v1").rstrip("/")


def model():
    return planner._env("MUSE_MODEL") or "muse-spark-1.3"


def post(path, body, timeout=180):
    req = urllib.request.Request(base() + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {planner._env('MUSE_API_KEY')}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def upload(path):
    """Files API upload (multipart), as Meta's reference client does with purpose=user_data."""
    b = uuid.uuid4().hex
    data = (f"--{b}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nuser_data\r\n"
            f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(path)}\"\r\n"
            f"Content-Type: {mimetypes.guess_type(path)[0] or 'application/octet-stream'}\r\n\r\n").encode() + \
        open(path, "rb").read() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(base() + "/files", data=data, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}",
                                          "Authorization": f"Bearer {planner._env('MUSE_API_KEY')}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["id"]


def step(name, fn):
    t = time.time()
    try:
        detail = fn()
        print(f"PASS  {name}  ({time.time() - t:.1f} s)  {detail or ''}")
        return True
    except urllib.error.HTTPError as e:
        print(f"FAIL  {name}  HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")
    except Exception as e:                                     # noqa: BLE001 - every failure is reported
        print(f"FAIL  {name}  {type(e).__name__}: {e}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", help="a local design folder to plan a review for")
    ap.add_argument("--run", action="store_true", help="also simulate the plans (heavy)")
    ap.add_argument("--image", help="a schematic image (png/jpg/pdf) to read")
    ap.add_argument("--sch", help="the xschem schematic the image shows (ground truth)")
    a = ap.parse_args()
    if not planner.configured("muse"):
        print("FAIL  no key: set MUSE_API_KEY (or MODEL_API_KEY) in this shell")
        return 1

    def hello():
        j = post("/responses", {"model": model(), "input": "Reply with the JSON object {\"ok\": true}.",
                                "text": {"format": {"type": "json_object"}}})
        out = json.loads(planner._output_text(j))
        assert out.get("ok") is True, out
        return f"model {model()}, usage {j.get('usage')}"

    def strict():
        out, use = planner._chat("muse", [{"role": "system", "content": planner.SYSTEM},
                                          {"role": "user", "content": "There are no circuit cells. Return no blocks and no plans."}])
        assert "blocks" in out and "plans" in out, out
        return f"format used: {use['format']}"

    ok = step("1. key + Responses API", hello)
    ok = step("2. structured output (planner schema)", strict) and ok

    if a.image:
        def image():
            fid = upload(a.image)
            j = post("/responses", {"model": model(), "text": {"format": {"type": "json_object"}}, "input": [{
                "role": "user", "content": [
                    {"type": "input_text", "text": "This is a transistor-level circuit schematic. Return JSON "
                     "{\"transistors\": <how many MOSFETs are drawn>, \"names\": [their labels], \"nets\": [named nets]}."},
                    {"type": "input_file", "file_id": fid}]}]})
            out = json.loads(planner._output_text(j))
            truth = None
            if a.sch:
                from kaaval_engine import netlist as N
                truth = sum(1 for l in N.netlist(a.sch).splitlines() if l[:2].upper() in ("XM", "M1", "M2") or
                            l[:1].upper() == "M")
            return f"Muse counts {out.get('transistors')} transistors" + (f", our netlist has {truth}" if truth else "") + \
                f"; names {out.get('names', [])[:8]}"
        ok = step("3. reads a schematic image", image) and ok

    if a.plan:
        def plan():
            ws = engine.upload(runner.design_files(a.plan))
            tbs = engine.testbenches(ws)
            res = planner.review("muse", ws, runner.project_docs(a.plan), runner.floor_note(tbs, None)) if a.run else None
            if res is None:                                     # plan only: ask Muse, validate, do not simulate
                cells = engine.cells(ws)
                out, use = planner._chat("muse", [{"role": "system", "content": planner.SYSTEM},
                                                  {"role": "user", "content": planner.context(runner.project_docs(a.plan), cells,
                                                                                              runner.floor_note(tbs, None))}])
                checked = []
                for p in out["plans"]:
                    p = dict(p, cell=planner.resolve_cell(p["cell"], cells))   # as planner.review resolves it
                    ep = planner._to_engine(p)
                    from kaaval_engine import plan as kp
                    root = os.path.join(os.path.expanduser(os.environ.get("KAAVAL_WS", "~/.kaaval/ws")), ws)
                    checked.append((p["cell"], p["kind"], kp.validate(ep, root) or "valid"))
                blocks = [(b["cell"], b["function"], b["startup_path"]) for b in out["blocks"]]
                return f"{len(cells)} cells read, {len(blocks)} blocks named {blocks[:4]}, plans: {checked}, usage {use}"
            return f"{len(res['plans'])} plans run, findings {[f['rule'] for p in res['plans'] for f in (p['result'] or {}).get('findings') or []]}"
        ok = step("4. plans a real review", plan) and ok
    print("READY" if ok else "NOT READY: see the FAIL lines")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

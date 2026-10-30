"""engine.py — how the Kaaval app talks to its review engine.

The review engine (kaaval_engine/) runs in this process: every call goes to its routes through Flask's test client,
so the bench is the same whether the engine is local or remote, and nothing leaves this machine. It needs ngspice and
the open sky130 PDK, nothing else.

One feature uses Minnal, SruSan's private, pre-existing analog design product: the sizing-fix search ("Try a sizing
fix"). When MINNAL_URL and MINNAL_KEY are set on this server, fix() sends the design's text files to Minnal's keyed
engine API and returns its verified proposal; without them the button explains that the fix search is not connected.
The key lives only in this server's environment and never reaches the browser.
"""
import json, os, urllib.error, urllib.request

from kaaval_engine import service

TIMEOUT = 600
_client = None


class EngineError(RuntimeError):
    pass


def configured():
    """The local engine is always present."""
    return True


def minnal_configured():
    return bool(os.environ.get("MINNAL_URL") and os.environ.get("MINNAL_KEY"))


def _local():
    global _client
    if _client is None:
        from flask import Flask
        a = Flask("kaaval-engine")
        a.register_blueprint(service.bp)
        _client = a.test_client()
    return _client


def _post(path, body, timeout=TIMEOUT):
    r = _local().post("/v1/kaaval/" + path, json=body)
    j = r.get_json(silent=True) or {}
    if r.status_code == 422 and "errors" in j:          # a refused plan: its reasons are the answer
        return j
    if r.status_code >= 400:
        raise EngineError(f"engine {r.status_code}: {j.get('error') or 'error'}")
    return j


def _minnal(path, body, timeout=TIMEOUT):
    if not minnal_configured():
        raise EngineError("Minnal's fix search is not connected: start Kaaval with MINNAL_URL and MINNAL_KEY set.")
    req = urllib.request.Request(os.environ["MINNAL_URL"].rstrip("/") + "/v1/kaaval/" + path,
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {os.environ['MINNAL_KEY']}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except Exception:
            msg = ""
        raise EngineError(f"Minnal {e.code}: {msg or e.reason}") from None
    except urllib.error.URLError as e:
        raise EngineError(f"Minnal unreachable ({e.reason})") from None
    except (TimeoutError, OSError) as e:
        raise EngineError(f"Minnal did not answer in time ({type(e).__name__})") from None


def upload(files):
    return _post("workspace", {"files": files})["ws"]


def audit(ws, scope="", tiles="1x2"):
    return _post("audit", {"ws": ws, "scope": scope, "tiles": tiles})


def testbenches(ws, scope="", focus=""):
    return _post("testbenches", {"ws": ws, "scope": scope, "focus": focus})["testbenches"]


def testbench(ws, tb, fix_traps=False):
    return _post("testbench", {"ws": ws, "tb": tb, "fix_traps": fix_traps})


def corner(ws, tb, corner_name, conds, fix_traps=False):
    return _post("corner", {"ws": ws, "tb": tb, "corner": corner_name, "conds": conds, "fix_traps": fix_traps})["results"]


def analyse(ws, tb):
    return _post("analyse", {"ws": ws, "tb": tb})


def fix(files, tb, device, fix_traps=False):
    """Minnal's sizing-fix search for one headroom finding: the design's text goes to Minnal, which sweeps the same
    45 conditions on its own engine and returns a fix verified at all of them (or why there is none)."""
    ws = _minnal("workspace", {"files": files})["ws"]
    _minnal("testbench", {"ws": ws, "tb": tb, "fix_traps": fix_traps})
    conds = [[t, v] for t in (-40, 27, 125) for v in (0.9, 1.0, 1.1)]
    for c in ("tt", "ss", "ff", "sf", "fs"):
        _minnal("corner", {"ws": ws, "tb": tb, "corner": c, "conds": conds, "fix_traps": fix_traps})
    return _minnal("fix", {"ws": ws, "tb": tb, "device": device, "fix_traps": fix_traps})


def tcorner(ws, tb, corner_name, conds, fix_traps=False):
    return _post("tcorner", {"ws": ws, "tb": tb, "corner": corner_name, "conds": conds, "fix_traps": fix_traps})["results"]


def tanalyse(ws, tb):
    return _post("tanalyse", {"ws": ws, "tb": tb})


def cells(ws, scope=""):
    return _post("cells", {"ws": ws, "scope": scope})["cells"]


def plan(ws, p):
    """Run one test plan; a refused plan comes back as {ok: False, errors: [...]} for the planner to correct."""
    return _post("plan", {"ws": ws, "plan": p})


def health():
    return _post("health", {}, timeout=30)


def deck(ws, p, corner, temp, vscale=1.0, case=None):
    return _post("deck", {"ws": ws, "plan": p, "corner": corner, "temp": temp, "vscale": vscale, "case": case})


def wave(ws, p, corner, temp, vscale, case=None):
    return _post("wave", {"ws": ws, "plan": p, "corner": corner, "temp": temp, "vscale": vscale, "case": case})

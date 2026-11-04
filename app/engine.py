"""engine.py — how the Kaaval app talks to its review engine.

The review engine (kaaval_engine/) runs in this process: every call goes to its routes through Flask's test client,
so the bench is the same whether the engine is local or remote, and nothing leaves this machine. It needs ngspice and
the open sky130 PDK, nothing else.
"""

from kaaval_engine import service

TIMEOUT = 600
_client = None


class EngineError(RuntimeError):
    pass


def configured():
    """The local engine is always present."""
    return True


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


def upload(files):
    return _post("workspace", {"files": files})["ws"]


def audit(ws, scope="", tiles="1x2"):
    return _post("audit", {"ws": ws, "scope": scope, "tiles": tiles})


def testbenches(ws, scope="", focus=""):
    return _post("testbenches", {"ws": ws, "scope": scope, "focus": focus})["testbenches"]


def testbench(ws, tb, fix_traps=False):
    return _post("testbench", {"ws": ws, "tb": tb, "fix_traps": fix_traps})


def loops(ws, tb, budget=None, fix_traps=False):
    """The feedback loops the testbench closes, each with its loop gain at 45 conditions (kaaval_engine.loops)."""
    return _post("loops", dict({"ws": ws, "tb": tb, "fix_traps": fix_traps}, **({"budget": budget} if budget else {})))


def loop_deck(ws, tb, loop, corner, temp, vscale=1.0):
    return _post("loopdeck", {"ws": ws, "tb": tb, "loop": loop, "corner": corner, "temp": temp, "vscale": vscale})


def corner(ws, tb, corner_name, conds, fix_traps=False):
    return _post("corner", {"ws": ws, "tb": tb, "corner": corner_name, "conds": conds, "fix_traps": fix_traps})["results"]


def analyse(ws, tb):
    return _post("analyse", {"ws": ws, "tb": tb})


def tcorner(ws, tb, corner_name, conds, fix_traps=False):
    return _post("tcorner", {"ws": ws, "tb": tb, "corner": corner_name, "conds": conds, "fix_traps": fix_traps})["results"]


def tanalyse(ws, tb):
    return _post("tanalyse", {"ws": ws, "tb": tb})


def cells(ws, scope=""):
    return _post("cells", {"ws": ws, "scope": scope})["cells"]


def plan(ws, p, budget=None):
    """Run one test plan; a refused plan comes back as {ok: False, errors: [...]} for the planner to correct. `budget`:
    seconds its simulations may take; conditions not reached in time come back as not run (errors, never findings)."""
    return _post("plan", dict({"ws": ws, "plan": p}, **({"budget": budget} if budget else {})))


def health():
    return _post("health", {}, timeout=30)


def deck(ws, p, corner, temp, vscale=1.0, case=None):
    return _post("deck", {"ws": ws, "plan": p, "corner": corner, "temp": temp, "vscale": vscale, "case": case})


def wave(ws, p, corner, temp, vscale, case=None):
    return _post("wave", {"ws": ws, "plan": p, "corner": corner, "temp": temp, "vscale": vscale, "case": case})

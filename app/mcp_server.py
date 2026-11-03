"""mcp_server.py — Kaaval as a Model Context Protocol server, so an AI assistant (Claude, an IDE agent, any MCP client)
can review an analog design and read its proven findings.

    python -m app.mcp_server                  # stdio; register this command in the client's MCP settings

Tools: kaaval_review (a local folder or a repository link: the whole review, as the web app runs it), kaaval_findings,
kaaval_finding (one finding with its failing conditions and evidence), kaaval_loops (the feedback loops one testbench
closes, measured at 45 conditions in seconds), kaaval_layout (layout against schematic). Reviews are stored in the same
database as the web app (KAAVAL_DB), so each one also opens on the bench at KAAVAL_URL/runs/<id>.

The protocol is JSON-RPC 2.0, one message per line on stdin / stdout (MCP stdio transport); nothing else is written to
stdout. Nothing in a reviewed repository is executed: files are read as text, as in every review.
"""
import json, os, shutil, sys, traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

PROTOCOL = "2025-06-18"
URL = os.environ.get("KAAVAL_URL", "http://127.0.0.1:5110").rstrip("/")
SKIP = {".git", "node_modules", "__pycache__", ".venv", "gds"}

TOOLS = [
    dict(name="kaaval_review", description=(
        "Review an analog chip design (xschem / SPICE / Magic on sky130) the way a senior analog engineer would: units "
        "traps, layout against schematic, the designer's testbench at 45 process/temperature/supply conditions, the "
        "loops its testbenches close, and power-up tests on every cell. Every finding is proven by simulation. Takes "
        "minutes. Give `path` (a local folder) or `repo` (a GitHub link or owner/repo)."),
        inputSchema=dict(type="object", properties=dict(
            path=dict(type="string", description="a local folder holding the design"),
            repo=dict(type="string", description="a repository link (https://github.com/owner/repo) or owner/repo")))),
    dict(name="kaaval_findings", description="The findings of a review, optionally only one kind (risk, note, trap) or "
                                             "rule prefix (analog/, layout/).",
         inputSchema=dict(type="object", required=["run_id"], properties=dict(
             run_id=dict(type="string"), kind=dict(type="string"), rule=dict(type="string")))),
    dict(name="kaaval_finding", description="One finding in full: what fails, where, at which conditions, the worst one, "
                                            "and its measured evidence.",
         inputSchema=dict(type="object", required=["run_id", "finding_id"], properties=dict(
             run_id=dict(type="string"), finding_id=dict(type=["string", "integer"])))),
    dict(name="kaaval_loops", description=(
        "The feedback loops one xschem testbench closes around an instance (an op-amp follower, a regulator's divider), "
        "found from the netlist, cut at the instance's output, loop gain measured at 45 conditions: phase margin, gain "
        "margin, unity-gain frequency, and a stability verdict. Seconds, no full review."),
        inputSchema=dict(type="object", required=["path", "testbench"], properties=dict(
            path=dict(type="string", description="the repository folder"),
            testbench=dict(type="string", description="the testbench .sch, relative to path")))),
    dict(name="kaaval_layout", description="Layout against schematic (Magic extraction + Netgen LVS) for every cell "
                                           "drawn both ways in a folder, with each mismatch explained.",
         inputSchema=dict(type="object", required=["path"], properties=dict(path=dict(type="string")))),
]


def _brief(f):
    return dict(id=f.get("id"), rule=f["rule"], kind=f.get("kind"), severity=f.get("severity"),
                where=f.get("location"), title=(f.get("title") or "")[:600])


def review(args):
    from app import inputs, runner, store
    if args.get("repo"):
        src, root = inputs.parse(args["repo"]), None
    elif args.get("path"):
        p = os.path.abspath(os.path.expanduser(args["path"]))
        if not os.path.isdir(p):
            raise ValueError(f"{p} is not a folder")
        src, root = inputs.Source("zip", label=os.path.basename(p)), p
    else:
        raise ValueError("give `path` (a local folder) or `repo` (a repository link)")
    rid = store.new_run(f"assistant: {src.describe()}")
    if root:                                   # the run's own copy, so the bench can draw its sheets
        dest = os.path.join(runner.WORK, rid)
        shutil.copytree(root, dest, ignore=lambda d, names: [n for n in names if n in SKIP])
        root = dest
    runner.review(rid, src, root=root)
    run, fs = store.run(rid), store.findings(rid)
    warns = [e["msg"] for e in store.events(rid) if e.get("level") in ("warn", "error")]
    count = lambda k: sum(1 for f in fs if f.get("kind") == k)
    return dict(run_id=rid, status=run.get("status"), bench=f"{URL}/runs/{rid}",
                summary=f"{count('risk')} design risk(s), {count('note')} note(s), {count('trap')} simulation trap(s)",
                findings=[_brief(f) for f in fs], review_warnings=warns[:12])


def findings(args):
    from app import store
    fs = store.findings(args["run_id"])
    fs = [f for f in fs if (not args.get("kind") or f.get("kind") == args["kind"])
          and (not args.get("rule") or f["rule"].startswith(args["rule"]))]
    return dict(run_id=args["run_id"], findings=[_brief(f) for f in fs])


def finding(args):
    from app import store
    f = next((f for f in store.findings(args["run_id"]) if str(f.get("id")) == str(args["finding_id"])), None)
    if not f:
        raise ValueError("no such finding in that run")
    d = f.get("detail") or {}
    keep = ("worst", "n_bad", "n", "conds", "device", "margins", "loop", "testbench", "nominal_id", "worst_id",
            "nominal_margin", "worst_margin", "states", "held", "floating", "plan", "verdict", "bodies", "split", "diffs")
    out = dict(_brief(f), detail={k: d[k] for k in keep if k in d},
               bench=f"{URL}/runs/{args['run_id']}?f={f.get('id')}",
               walkthrough=f"{URL}/runs/{args['run_id']}?f={f.get('id')}&walk=1")
    if d.get("k") is not None or d.get("loop"):
        out["evidence_zip"] = f"{URL}/api/runs/{args['run_id']}/findings/{f.get('id')}/evidence"
    return out


def loops(args):
    from kaaval_engine import checks, loops as L, sim
    root = os.path.abspath(os.path.expanduser(args["path"]))
    p = os.path.realpath(os.path.join(root, args["testbench"]))
    if not p.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(p):
        raise ValueError("the testbench must be a file inside path")
    tb = sim.Testbench.from_sch(p)
    subs = {n.lower(): v for n, _, v in L._top(tb.circuit) if n[0].lower() == "x"}
    out = []
    with sim.until(240):
        for lp in L.find(tb.circuit, L.directions(p))[:6]:
            sw = L.sweep(tb, lp)
            judged = [r for r, e in sw.values() if r and not e]
            pms = [r["pm"] for r in judged if r.get("pm") is not None]
            fs = checks.stability(sw) if judged else []
            out.append(dict(instance=lp["inst"], subcircuit=subs.get(lp["inst"].lower(), ""), output=lp["net"],
                            path=lp["via"], judged=f"{len(judged)} of {len(sw)} conditions",
                            phase_margin_deg=[round(min(pms), 1), round(max(pms), 1)] if pms else None,
                            not_judged=next((e for r, e in sw.values() if e), None) if not judged else None,
                            findings=[dict(rule=x["rule"], message=x["message"]) for x in fs]))
    return dict(testbench=args["testbench"], loops=out,
                note="no loop closed around an instance" if not out else "")


def layout(args):
    from kaaval_engine import layout_check as LC
    root = os.path.abspath(os.path.expanduser(args["path"]))
    if not LC.available():
        raise ValueError("Magic, Netgen or the sky130 Netgen setup is not installed on this machine")
    res, fs, note = LC.review(root)
    return dict(summary=note, cells=[dict(cell=r["cell"], verdict=r.get("verdict"), error=r.get("error")) for r in res],
                findings=[dict(rule=f["rule"], severity=f["severity"], title=f["title"][:500]) for f in fs])


CALLS = dict(kaaval_review=review, kaaval_findings=findings, kaaval_finding=finding, kaaval_loops=loops,
             kaaval_layout=layout)


def handle(msg):
    """One JSON-RPC message -> its reply, or None for a notification."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:                                   # notifications (notifications/initialized, cancelled ...)
        return None
    if method == "initialize":
        res = dict(protocolVersion=PROTOCOL, capabilities=dict(tools=dict(listChanged=False)),
                   serverInfo=dict(name="kaaval", version="1.0"),
                   instructions="Kaaval reviews analog chip designs; every finding is proven in ngspice. Start with "
                                "kaaval_review, then kaaval_finding for the ones that matter.")
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = dict(tools=TOOLS)
    elif method == "tools/call":
        fn = CALLS.get(params.get("name"))
        if not fn:
            return dict(jsonrpc="2.0", id=mid, error=dict(code=-32602, message=f"unknown tool {params.get('name')!r}"))
        try:
            out = fn(params.get("arguments") or {})
            res = dict(content=[dict(type="text", text=json.dumps(out, indent=1, default=str))], structuredContent=out,
                       isError=False)
        except Exception as e:                        # a tool's failure is the tool's answer, not a protocol error
            print(traceback.format_exc(), file=sys.stderr, flush=True)
            res = dict(content=[dict(type="text", text=f"{type(e).__name__}: {e}")], isError=True)
    else:
        return dict(jsonrpc="2.0", id=mid, error=dict(code=-32601, message=f"method not found: {method}"))
    return dict(jsonrpc="2.0", id=mid, result=res)


def main(inp=None, out=None):
    inp, out, real = inp or sys.stdin, out or sys.stdout, sys.stdout
    sys.stdout = sys.stderr                           # anything a library prints goes to stderr: stdout is the protocol
    try:
        for line in inp:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                reply = dict(jsonrpc="2.0", id=None, error=dict(code=-32700, message="parse error"))
            else:
                reply = handle(msg)
            if reply is not None:
                out.write(json.dumps(reply, default=str) + "\n")
                out.flush()
    finally:
        sys.stdout = real


if __name__ == "__main__":
    main()

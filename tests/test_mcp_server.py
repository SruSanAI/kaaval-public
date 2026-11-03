"""app/mcp_server: the MCP stdio protocol (initialize, tools/list, errors) and the finding tools on a seeded store.
No simulation; kaaval_review and kaaval_loops run the same code as the web app and tests/test_testbench_loops.py."""
import io, json, os, sys, tempfile
os.environ["KAAVAL_DB"] = os.path.join(tempfile.mkdtemp(), "k.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import mcp_server as M, store  # noqa: E402


def talk(*msgs):
    out = io.StringIO()
    M.main(io.StringIO("".join(json.dumps(m) + "\n" for m in msgs) + "not json\n"), out)
    return [json.loads(l) for l in out.getvalue().splitlines()]


def test_protocol():
    r = talk(dict(jsonrpc="2.0", id=1, method="initialize", params={}), dict(jsonrpc="2.0", method="notifications/initialized"),
             dict(jsonrpc="2.0", id=2, method="tools/list"), dict(jsonrpc="2.0", id=3, method="tools/call",
                                                                 params=dict(name="nope")),
             dict(jsonrpc="2.0", id=4, method="resources/list"))
    assert [x.get("id") for x in r] == [1, 2, 3, 4, None]                # no reply to a notification; parse error last
    assert r[0]["result"]["serverInfo"]["name"] == "kaaval" and "tools" in r[0]["result"]["capabilities"]
    assert {t["name"] for t in r[1]["result"]["tools"]} == set(M.CALLS)
    assert r[2]["error"]["code"] == -32602 and r[3]["error"]["code"] == -32601 and r[4]["error"]["code"] == -32700


def test_findings_and_one_finding():
    rid = store.new_run("seeded")
    store.add_finding(rid, dict(rule="analog/low_phase_margin", severity="warn", kind="risk", title="thin margins",
                                location="xschem/tb.sch · x1 loop (cut at x1.2)", device="x1",
                                detail=dict(loop=dict(inst="x1", subckt="opamp"), worst=["sf", -40, 1.1], n_bad=45, n=45,
                                            testbench="xschem/tb.sch", results=[{"pm": 1.0}])))
    store.add_finding(rid, dict(rule="layout/split_pin", severity="info", kind="note", title="VDD in 2 pieces",
                                location="mag/buf.mag", device="buf", detail={}))
    r = talk(dict(jsonrpc="2.0", id=1, method="tools/call", params=dict(name="kaaval_findings", arguments=dict(run_id=rid, kind="risk"))))
    fs = r[0]["result"]["structuredContent"]["findings"]
    assert [f["rule"] for f in fs] == ["analog/low_phase_margin"], fs
    r = talk(dict(jsonrpc="2.0", id=2, method="tools/call", params=dict(name="kaaval_finding",
                                                                     arguments=dict(run_id=rid, finding_id=fs[0]["id"]))))
    one = r[0]["result"]["structuredContent"]
    assert one["detail"]["worst"] == ["sf", -40, 1.1] and one["detail"]["loop"]["inst"] == "x1" and "results" not in one["detail"]
    assert one["walkthrough"].endswith(f"/runs/{rid}?f={fs[0]['id']}&walk=1") and one["evidence_zip"].endswith("/evidence")
    r = talk(dict(jsonrpc="2.0", id=3, method="tools/call", params=dict(name="kaaval_finding", arguments=dict(run_id=rid, finding_id="999"))))
    assert r[0]["result"]["isError"] and "no such finding" in r[0]["result"]["content"][0]["text"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

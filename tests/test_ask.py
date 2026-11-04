"""POST /api/runs/<id>/ask: a question about a finished review goes to the planner with the review's findings as text;
cited ids that are not findings are dropped; refused while the review runs, without Muse, or past the limit.
No network: planner._chat is stubbed."""
import json, os, sys, tempfile
os.environ["KAAVAL_DB"] = os.path.join(tempfile.mkdtemp(), "k.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import planner, server, store  # noqa: E402


def test_ask_answers_from_the_review():
    rid = store.new_run("t")
    store.set_live(rid, dict(dut="xschem/amp.sch", testbench="xschem/tb.sch"))
    store.add_finding(rid, dict(rule="analog/low_phase_margin", severity="warn", kind="risk", title="thin margins",
                                location="xschem/tb.sch · x1 loop", device="x1", detail=dict(worst=["sf", -40, 1.1])))
    fid = str(store.findings(rid)[0]["id"])
    seen, old, env = [], planner._chat, dict(os.environ)
    planner._chat = lambda arm, msgs, timeout=420, schema=None: (seen.append((msgs, schema)) or
                                                                  ({"answer": "x1 rings.", "cites": [fid, "bogus"]}, {}))
    os.environ["MUSE_API_KEY"] = "k"
    c = server.app.test_client()
    try:
        j = c.post(f"/api/runs/{rid}/ask", json={"q": "why?"}).get_json()                  # while it runs: answered,
        assert j["ok"] and seen[-1][0][1]["content"].startswith("# The review\nTHE REVIEW IS STILL RUNNING")  # and said so
        seen.clear()
        store.update_run(rid, status="done")
        j = c.post(f"/api/runs/{rid}/ask", json={"q": "why does it ring?"}).get_json()
        assert j == dict(ok=True, answer="x1 rings.", cites=[fid]), j
        text = seen[0][0][1]["content"]
        assert f"id {fid}: analog/low_phase_margin" in text and '"worst": ["sf", -40, 1.1]' in text and "why does it ring?" in text
        assert seen[0][1]["name"] == "kaaval_answer"
        assert c.post(f"/api/runs/{rid}/ask", json={"q": ""}).status_code == 400
        server.ACCESS = "secret"                                                              # a public server
        assert c.post(f"/api/runs/{rid}/ask", json={"q": "why?"}).status_code == 403
        assert c.post(f"/api/runs/{rid}/ask", json={"q": "why?"}, headers={"X-Kaaval-Code": "secret"}).status_code == 200
        server.ACCESS, server.ASK_PER_HOUR = "", 0
        assert c.post(f"/api/runs/{rid}/ask", json={"q": "why?"}).status_code == 429             # per-address limit
        server.ASK_PER_HOUR = 30
        os.environ.pop("MUSE_API_KEY")
        assert c.post(f"/api/runs/{rid}/ask", json={"q": "why?"}).status_code == 503
    finally:
        planner._chat = old; os.environ.clear(); os.environ.update(env)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

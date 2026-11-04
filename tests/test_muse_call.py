"""planner._chat's request to the Responses API: strict json_schema with high reasoning effort first; an endpoint that
refuses it (400) gets the plain JSON-mode request. No network: _call is stubbed."""
import io, json, os, sys, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import planner as P  # noqa: E402


def test_effort_high_then_plain_fallback():
    sent, old, env = [], P._call, dict(os.environ)
    os.environ["MUSE_API_KEY"] = "test-key"; os.environ.pop("MUSE_EFFORT", None)

    def fake(arm, body, timeout):
        sent.append(json.loads(json.dumps(body)))
        if len(sent) == 1:
            raise urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b"no"))
        return {"output_text": json.dumps({"blocks": [], "plans": []}), "usage": {"input_tokens": 3, "output_tokens": 4}}
    P._call = fake
    try:
        out, use = P._chat("muse", [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    finally:
        P._call = old; os.environ.clear(); os.environ.update(env)
    assert sent[0]["reasoning"] == {"effort": "high", "summary": "auto"} and sent[0]["text"]["format"]["type"] == "json_schema"
    assert "reasoning" not in sent[1] and sent[1]["text"]["format"]["type"] == "json_object"
    assert out == {"blocks": [], "plans": []} and use["format"] == "json_object" and use["effort"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

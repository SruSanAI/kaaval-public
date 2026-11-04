"""planner.Watch: the plan Muse Spark is writing becomes events as each block and test completes (streamed JSON, cut at
arbitrary points); planner.reasoning_summary reads the Responses API's summary items. No network."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import planner as P  # noqa: E402


def test_watch_events_as_the_plan_streams():
    full = json.dumps({"blocks": [{"cell": "core_prel", "evidence": "M8 {gate}", "function": 'bandgap core, "leakage" start-up',
                                   "ports": [{"port": "vdd", "role": "supply"}]}],
                       "plans": [{"kind": "powerup", "cell": "core_prel", "supplies": [{"port": "vdd", "volts": 1.8}],
                                  "why": "no start-up path"},
                                 {"cell": "opamp_l", "why": "error amp loop", "kind": "stability", "supplies": []}]})
    got = []
    w = P.Watch(lambda kind, text: got.append(text))
    for i in range(1, len(full) + 1, 7):                 # the stream arrives in pieces
        w(full[:i])
    w(full)
    assert got[0].startswith("Muse Spark finished thinking after"), got
    got = got[1:]
    assert got == ['Muse Spark names core_prel: bandgap core, "leakage" start-up',
                   "Muse Spark plans a powerup test on core_prel: no start-up path",
                   "Muse Spark plans a stability test on opamp_l: error amp loop"], got


def test_reasoning_summary():
    j = {"output": [{"type": "reasoning", "summary": [{"type": "summary_text", "text": "Comparing Cc with the load."}]},
                    {"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]}
    assert P.reasoning_summary(j) == "Comparing Cc with the load." and P.reasoning_summary({}) == ""


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

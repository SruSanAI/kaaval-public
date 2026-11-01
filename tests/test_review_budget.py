"""The review's time budget (backtest v2, 1 Nov: one 1366-device design ran 20 h with no limit): every simulation
inside sim.until() ends by the deadline, pool threads keep it, a run not started says so, and the planner shares the
budget out with every power-up first and never starts a test whose share is gone."""
import os, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import sim  # noqa: E402
from app import planner  # noqa: E402

SLOW = """* a control loop far longer than any budget here
V1 a 0 1
R1 a 0 1k
.control
let i = 0
while i < 1e9
let i = i + 1
end
.endc
.end
"""


def test_run_is_cut_at_the_deadline():
    t0 = time.time()
    with sim.until(2):
        out, err = sim.run(SLOW, timeout=600)
    assert err == "timeout" and time.time() - t0 < 10, (err, time.time() - t0)


def test_run_not_started_when_spent():
    with sim.until(0.5):
        assert sim.run(SLOW, timeout=600) == ("", sim.OVER)
    assert sim.time_left() is None                       # the budget ends with its block


def test_pool_threads_keep_the_budget():
    with sim.until(100), ThreadPoolExecutor(1) as ex:
        assert sim.spawn(ex, sim.time_left).result() > 90
        assert ex.submit(sim.time_left).result() is None   # a plain submit would lose it


def test_clock_shares_with_powerup_double():
    c = planner.Clock(300)
    s = c.share(dict(kind="powerup"), [dict(kind="drive"), dict(kind="powerup")])
    assert 115 < s <= 120, s                              # 300 * 2 / (2 + 1 + 2)
    assert planner.Clock(0).share(dict(kind="powerup")) is None


def test_rules_powerups_first_and_skips_when_spent(monkeypatch=None):
    cells = [dict(cell=f"x/{n}.sch", ports=["vdd", "vss", "en", "out"], devices=d, netlist="")
             for n, d in (("big", 900), ("small", 20))]
    seen = []

    def fake_plan(ws, ep, budget=None):
        seen.append((ep["kind"], ep["cell"], budget))
        time.sleep(0.05)
        return dict(ok=True, results=[], findings=[])

    old = planner.engine.cells, planner.engine.plan, planner.PLAN_BUDGET
    planner.engine.cells, planner.engine.plan = (lambda ws: cells), fake_plan
    try:
        planner.PLAN_BUDGET = 1000
        res = planner._rules("ws", lambda *a, **k: None)
        kinds = [k for k, _, _ in seen]
        assert kinds[:2] == ["powerup", "powerup"] and "powerup" not in kinds[2:], kinds
        assert all(b is not None and b > 0 for _, _, b in seen)
        # two cells x (power-up 2 + sequence 1 + drive 1): the first power-up gets 2/8 of the budget, and the last
        # test whatever the others left
        assert len(seen) == 6 and 240 < seen[0][2] <= 250 and seen[-1][2] > 900, seen
        seen.clear()
        planner.PLAN_BUDGET = 1e-3                         # spent at once: nothing is started, all said so
        res = planner._rules("ws", lambda *a, **k: None)
        assert not seen and res["plans"] and all(p["result"].get("skipped") for p in res["plans"])
    finally:
        planner.engine.cells, planner.engine.plan, planner.PLAN_BUDGET = old


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

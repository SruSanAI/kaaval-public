"""A whole review of the demo tile, in-process, without Muse Spark: every stage runs to the end and the planted flaws
are found (units trap, layout size, headroom, the follower's thin margin, the dead reference). It simulates (about a
minute). Before, a runner bug stopped every review right after the operating point, which no unit test reached."""
import os, shutil, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def test_demo_tile_review_runs_to_the_end():
    with tempfile.TemporaryDirectory() as t:
        os.environ["KAAVAL_DB"], os.environ["KAAVAL_WORK"] = os.path.join(t, "k.db"), os.path.join(t, "work")
        key = os.environ.pop("MUSE_API_KEY", None)
        try:
            import importlib
            from app import store, runner, inputs
            importlib.reload(store); importlib.reload(runner)
            rid = store.new_run("e2e")
            dest = os.path.join(runner.WORK, rid)
            shutil.copytree(os.path.join(HERE, "examples", "demo_tapeout"), dest)
            runner.review(rid, inputs.Source("zip", label="demo.zip"), root=dest)
            errors = [e["msg"] for e in store.events(rid) if e.get("level") == "error"]
            assert store.run(rid)["status"] == "done" and not errors, errors
            rules = {f["rule"] for f in store.findings(rid)}
            for want in ("units/mos_si_units", "layout/sizes_differ", "analog/headroom", "analog/low_phase_margin",
                         "analog/no_startup"):
                assert want in rules, (want, sorted(rules))
            amp = [f for f in store.findings(rid) if f["rule"] == "analog/headroom"]
            assert amp and not amp[0]["detail"].get("corrected")   # tb_amp itself had no units trap to correct
        finally:
            if key:
                os.environ["MUSE_API_KEY"] = key


if __name__ == "__main__":
    test_demo_tile_review_runs_to_the_end()
    print("ok test_demo_tile_review_runs_to_the_end")

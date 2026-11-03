"""tools/kaaval_check.py: findings as SARIF (GitHub shows them on the pull request's files), the exit code a CI job
reads, and a folder that is not there refused. No simulation."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
import kaaval_check as K  # noqa: E402


def test_sarif_levels_and_file_locations():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "xschem"))
    open(os.path.join(d, "xschem", "opamp.sch"), "w").write("v {}\n")
    fs = [dict(rule="analog/low_phase_margin", kind="risk", severity="warn", title="thin margins",
               location="xschem/opamp.sch · x1 loop (cut at x1.2)"),
          dict(rule="analog/oscillates", kind="note", severity="info", title="needs a floating input",
               location="xschem/gone.sch · baseline power-up (no model)"),
          dict(rule="units/scale", kind="trap", severity="warn", title="1 m2 diode", location="")]
    s = K.sarif(fs, d)
    run, = s["runs"]
    assert s["version"] == "2.1.0" and {r["id"] for r in run["tool"]["driver"]["rules"]} == {f["rule"] for f in fs}
    a, b, c = run["results"]
    assert a["level"] == "warning" and a["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "xschem/opamp.sch"
    assert b["level"] == "note" and "locations" not in b            # a file that is not in the repository: no location
    assert c["level"] == "error"


def test_a_missing_folder_is_refused():
    try:
        K.main(["/nonexistent/kaaval"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("a missing folder was accepted")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

"""Kaaval never edits a design: planned tests, the bench deck and the power-up waveform read the designer's files, and
afterwards every file is byte-for-byte what it was and nothing was added. The engine builds its testbench beside the
cell in memory and simulates in its own temporary folder. Power-up, domains and drive run here; sequence and stability
build the same bench (plan.compile_bench) and are left to their own tests, which take minutes."""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import plan as P

CELL = """* a reference with an inverter on a second rail
.subckt ref vdd vdda vss vref out
R1 vdd vref 100k
R2 vref vss 100k
XMP out vref vdda vdda sky130_fd_pr__pfet_01v8 W=1 L=0.15
XMN out vref vss vss sky130_fd_pr__nfet_01v8 W=0.5 L=0.15
.ends
"""
BASE = dict(cell="ref.spice#ref", supplies={"vdd": 1.8, "vdda": 1.8}, grounds=["vss"], corners=["tt"], temps=[27],
            vscales=[1.0])


def snapshot(root):
    return {os.path.relpath(os.path.join(d, f), root): hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest()
            for d, _, fs in os.walk(root) for f in fs}


def test_planned_tests_never_touch_the_design(tmp_path):
    (tmp_path / "ref.spice").write_text(CELL)
    (tmp_path / "info.yaml").write_text("project:\n  top_module: tt_um_kaaval_demo\n")
    before = snapshot(tmp_path)
    plans = [dict(BASE, kind="powerup"), dict(BASE, kind="domains"), dict(BASE, kind="drive", pads=[{"port": "vref"}])]
    for p in plans:
        r = P.run(p, str(tmp_path))
        assert r.get("ok"), (p["kind"], r.get("errors"))
    text, err = P.bench_deck(plans[-1], str(tmp_path), "tt", 27)
    assert text and not err, err
    w, err = P.wave(plans[0], str(tmp_path), "tt", 27)
    assert w and not err, err
    assert snapshot(tmp_path) == before

if __name__ == "__main__":
    import tempfile, pathlib
    test_planned_tests_never_touch_the_design(pathlib.Path(tempfile.mkdtemp()))
    print("ok test_planned_tests_never_touch_the_design")

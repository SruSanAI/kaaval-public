"""Evidence a designer can check without Kaaval: the testbench of a planned test as a plain ngspice deck that names
the standard sky130 library, carries no path of this server, and leaves the designer's cell exactly as written;
and the worst condition of any test kind read back as corner, temperature and supply scale."""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import plan as P
from kaaval_engine.paths import PDK_LIB

REF = """.subckt ref vdd vss vref
R1 vdd vref 100k
R2 vref vss 100k
.ends
"""
PLAN = dict(cell="r.spice#ref", kind="drive", supplies={"vdd": 1.8}, grounds=["vss"], pads=[{"port": "vref"}],
            corners=["tt"], temps=[27], vscales=[1.0])


def test_bench_deck_is_portable_and_runs(tmp_path):
    (tmp_path / "r.spice").write_text(REF)
    text, err = P.bench_deck(PLAN, str(tmp_path), "ss", 125, 0.9)
    assert not err and text, err
    assert '.lib "sky130A/libs.tech/ngspice/sky130.lib.spice" ss' in text and ".temp 125" in text
    assert str(tmp_path) not in text and os.path.realpath(str(tmp_path)) not in text
    assert all(line in text for line in REF.strip().splitlines()), "the designer's cell must appear unchanged"
    (tmp_path / "bench.sp").write_text(text.replace("sky130A/libs.tech/ngspice/sky130.lib.spice", PDK_LIB)
                                       .replace("op\n", "op\nprint v(vref)\n", 1))
    out = subprocess.run(["ngspice", "-b", "bench.sp"], cwd=tmp_path, capture_output=True, text=True, timeout=120).stdout
    v = float(re.search(r"v\(vref\)\s*=\s*([-+0-9.eE]+)", out).group(1))
    assert abs(v - 0.9 * 0.9) < 0.01, out[-800:]


def test_bench_deck_refuses_a_bad_plan(tmp_path):
    (tmp_path / "r.spice").write_text(REF)
    text, err = P.bench_deck(dict(PLAN, cell="nope.spice#ref"), str(tmp_path), "tt", 27)
    assert text is None and err


def test_worst_condition_of_each_test_kind():
    from app.server import _worst
    assert _worst(["ss", -40, 0.9]) == ("ss", -40, 0.9)                                  # powerup
    assert _worst(["rails together", "ff", 125, 1.0]) == ("ff", 125, 1.0)               # sequence
    assert _worst(["VDD off, VDDA on (supply x1)", "sf", 27]) == ("sf", 27, 1.0)        # domains
    assert _worst(None) == ("tt", 27, 1.0)

if __name__ == "__main__":
    import tempfile, pathlib
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(*([pathlib.Path(tempfile.mkdtemp())] if "tmp_path" in fn.__code__.co_varnames[:1] else []))
            print("ok", name)

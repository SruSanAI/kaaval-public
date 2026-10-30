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


BETA = """.subckt beta vdd vss
XM1 n1 n1 vss vss sky130_fd_pr__nfet_01v8 L=2 W=4 nf=1 m=1
XM2 n2 n1 s2 vss sky130_fd_pr__nfet_01v8 L=2 W=16 nf=1 m=1
R1 s2 vss 20k
XM3 n1 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM4 n2 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
.ends
"""


def test_powerup_deck_shows_the_dead_state_not_just_the_dc_answer(tmp_path):
    """A 'wakes up dead' finding's deck must show both sides: the DC answer reports a working bias, the power-up from
    0 V in the same deck settles at zero current (our beta-multiplier reference without a start-up device)."""
    (tmp_path / "b.spice").write_text(BETA)
    pl = dict(cell="b.spice#beta", kind="powerup", supplies={"vdd": 1.8}, grounds=["vss"], corners=["tt"], temps=[27],
              vscales=[1.0])
    text, err = P.bench_deck(pl, str(tmp_path), "tt", 27)
    assert not err and "tran " in text and "\nop\n" in text, err
    (tmp_path / "bench.sp").write_text(text.replace("sky130A/libs.tech/ngspice/sky130.lib.spice", PDK_LIB))
    out = subprocess.run(["ngspice", "-b", "bench.sp"], cwd=tmp_path, capture_output=True, text=True, timeout=300).stdout
    i_dc = abs(float(re.search(r"vplan0#branch\s*=\s*([-+0-9.eE]+)", out).group(1)))
    i_end = abs(float(re.search(r"i_end_vplan0\s*=\s*([-+0-9.eE]+)", out).group(1)))
    assert i_dc > 5e-6 and i_end < 1e-8, (i_dc, i_end, out[-800:])
    assert (tmp_path / "powerup.txt").exists()


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

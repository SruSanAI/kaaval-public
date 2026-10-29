"""Controls driven by the project's own logic: a digital simulation's VCD sets when an analog block's power-down pin is
released, and the sequence check runs the block with that timing (ngspice + sky130, circuits and logic of our own).

The reference below starts only from a kick of its rail ramp. Released with the rail it starts; our logic
(tests/data/en_release.v, simulated with iverilog into en_release.vcd) holds it powered down through reset and releases
it 54.5 µs after the rails, when the kick is long gone: it stays off. With its own start-up device it starts every way."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import plan as P, sim, vcd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CORE = """.subckt bref pd_n vdd vss iout
XM1 n1 n1 vss vss sky130_fd_pr__nfet_01v8 L=2 W=4 nf=1 m=1
XM2 n2 n1 s2 vss sky130_fd_pr__nfet_01v8 L=2 W=16 nf=1 m=1
R1 s2 vss 20k
XM3 n1 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM4 n2 n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XM5 iout n2 vdd vdd sky130_fd_pr__pfet_01v8 L=2 W=8 nf=1 m=1
XMI1 pd pd_n vdd vdd sky130_fd_pr__pfet_01v8 L=0.15 W=1 nf=1 m=1
XMI2 pd pd_n vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=0.5 nf=1 m=1
XMPD n1 pd vss vss sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1 m=1
{startup}
.ends
"""
KICK = "Ckick vdd n1 200f"
OWN = "XM6 n1 vss vdd vdd sky130_fd_pr__pfet_01v8 L=20 W=0.42 nf=1 m=1"


def logic_wave():
    sig = vcd.parse(open(os.path.join(DATA, "en_release.vcd")).read())
    return vcd.wave(sig[vcd.find(sig, "dut.en")])


def plan(wave):
    return dict(cell="ref.spice#bref", kind="sequence", supplies={"vdd": 1.8}, grounds=["vss"], pads=[{"port": "iout"}],
                controls=[{"port": "pd_n", "volts": 1.8, "wave": wave}], corners=["tt"], temps=[27], vscales=[1.0])


def write(tmp_path, startup):
    (tmp_path / "ref.spice").write_text(CORE.format(startup=startup))
    return str(tmp_path)


def test_vcd_gives_the_release_time():
    w = logic_wave()
    assert [b for _, b in w] == [0, 1] and abs(w[1][0] - 54.5e-6) < 1e-12, w
    sig = vcd.parse(open(os.path.join(DATA, "en_release.vcd")).read())
    assert vcd.find(sig, "en") is None                       # tb.en and tb.dut.en: ambiguous, not guessed
    try:
        vcd.wave(sig[vcd.find(sig, "dut.n")])
        raise AssertionError("a counter vector was taken as a control")
    except ValueError:
        pass
    clock = "$timescale 1ns $end $var reg 1 ! c $end $enddefinitions $end " + \
        " ".join(f"#{i} {i % 2}!" for i in range(vcd.MAX_EDGES + 5))
    try:
        vcd.wave(vcd.parse(clock)["c"])
        raise AssertionError("a clock was taken as a control")
    except ValueError:
        pass


def test_wave_is_validated_and_driven(tmp_path):
    root = write(tmp_path, KICK)
    assert P.validate(plan(logic_wave()), root) == []
    for bad in ([[1e-6, 1], [0.5e-6, 0]], [[0, 2]], [[1.0, 1]], []):
        assert any("wave" in e for e in P.validate(plan(bad), root)), bad
    deck = sim._ramped("Vc a 0 1.8", 2e-6, 1.0, [], {"vc": ("wave", [[0.0, 1], [3e-6, 0], [3e-6, 1]])})
    ts = [float(x) for x in deck.split("PWL(")[1].rstrip(")").split()[0::2]]
    assert all(b > a for a, b in zip(ts, ts[1:])), deck


def test_logic_holds_the_kick_start_reference_off(tmp_path):
    r = P.run(plan(logic_wave()), write(tmp_path, KICK))
    st = {x["case"]: x["state"] for x in r["results"]}
    assert st["rails together, fast (2 µs ramps), pd_n with the rails"] == "settled", st
    assert st["rails together, fast (2 µs ramps), pd_n as the project's logic drives them"] == "dead", st
    f = [x for x in r["findings"] if x["rule"] == "analog/sequence_dependent"]
    assert len(f) == 1 and "logic" in f[0]["case"] and "digital simulation" in f[0]["message"], r["findings"]


def test_own_startup_passes_with_the_logic(tmp_path):
    r = P.run(plan(logic_wave()), write(tmp_path, OWN))
    assert r["ok"] and r["findings"] == [], r["findings"]


if __name__ == "__main__":
    import inspect, pathlib, tempfile
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(*([pathlib.Path(tempfile.mkdtemp())] if inspect.signature(fn).parameters else []))
            print("ok", name)

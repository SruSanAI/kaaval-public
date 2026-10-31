"""Layout-only designs: Kaaval extracts a netlist from the Magic layout (our own one-transistor layout, drawn with
Magic). The decision needs no tool; the extraction runs where Magic and the sky130 tech files are installed."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import extract  # noqa: E402

MAG = """magic
tech sky130A
timestamp 0
<< checkpaint >>
rect -550 730 750 770
rect -630 -630 830 730
rect -550 -670 750 -630
<< nmos >>
rect 80 0 120 100
<< ndiff >>
rect 0 0 80 100
rect 120 0 200 100
<< poly >>
rect 80 100 120 140
rect 80 -40 120 0
<< labels >>
rlabel poly 80 120 120 140 1 G
port 1 n
rlabel ndiff 0 40 20 60 1 S
port 2 n
rlabel ndiff 180 40 200 60 1 D
port 3 n
<< end >>
"""
INFO = 'project:\n  top_module: "tt_um_kaaval_layout"\n'


def _repo():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "mag"))
    open(os.path.join(d, "mag", "tt_um_kaaval_layout.mag"), "w").write(MAG)
    open(os.path.join(d, "info.yaml"), "w").write(INFO)
    return d


def test_only_layout_needs_extraction():
    assert extract.needed({"mag/a.mag": MAG, "info.yaml": INFO})
    assert not extract.needed({"mag/a.mag": MAG, "xschem/a.sch": "v {}"})                 # a schematic: use it
    assert not extract.needed({"mag/a.mag": MAG, "netlist/a.spice": ".subckt a x y\n.ends"})   # a netlist: use it
    assert not extract.needed({"README.md": "", "info.yaml": INFO})                        # nothing to extract


def test_top_cell_from_info_yaml():
    d = _repo()
    assert extract.top_cell(d) == ("tt_um_kaaval_layout", os.path.join("mag", "tt_um_kaaval_layout.mag"))
    os.remove(os.path.join(d, "info.yaml"))
    assert extract.top_cell(d) == (None, None)


def test_extracts_the_transistor():
    if not extract.available():
        print("skip: Magic or the sky130 magic tech files are not installed")
        return
    d = _repo()
    text, note = extract.from_layout(d)
    assert text and ".subckt tt_um_kaaval_layout" in text and "sky130_fd_pr__nfet_01v8" in text, note
    assert "no parasitics" in note
    assert set(os.listdir(d)) == {"mag", "info.yaml"} and os.listdir(os.path.join(d, "mag")) == ["tt_um_kaaval_layout.mag"]
    # (nothing written into the repository: Magic's .ext files stay in its temporary folder)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

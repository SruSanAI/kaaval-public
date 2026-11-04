"""runner.adopt: an uploaded zip ends up as WORK/<run id> = the project root (a zip's one top folder dropped), the
folder the sheets, chip view and Layout 3D read. Before, uploads stayed in WORK/upload-*, so those views were empty."""
import os, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import inputs, runner  # noqa: E402


def _zip(tmp, names):
    p = os.path.join(tmp, "in.zip")
    with zipfile.ZipFile(p, "w") as z:
        for n in names:
            z.writestr(n, "x")
    return p


def test_wrapped_and_flat_zips_become_the_run_folder():
    for names, rid in ((["demo/info.yaml", "demo/xschem/a.sch", "__MACOSX/demo/._a"], "r1"),
                       (["info.yaml", "xschem/a.sch"], "r2")):
        with tempfile.TemporaryDirectory() as work:
            runner.WORK = work
            up = os.path.join(work, "upload-abc")
            root = inputs.unpack_zip(_zip(work, names), up)
            got = runner.adopt(rid, root)
            assert got == os.path.join(os.path.realpath(work), rid), got
            assert os.path.isfile(os.path.join(got, "info.yaml")) and os.path.isfile(os.path.join(got, "xschem", "a.sch"))
            assert not os.path.exists(up)


def test_other_roots_stay_put():
    with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as elsewhere:
        runner.WORK = work
        assert runner.adopt("r3", elsewhere) == elsewhere and os.path.isdir(elsewhere)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

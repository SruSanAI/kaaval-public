"""logic_wave.py — a plan control from a digital simulation: when the project's logic drives an analog control pin.

    python tools/logic_wave.py <dump.vcd> <signal> <analog port> [--volts 1.8] [--invert] [--from <signal>]

Prints the control as JSON ({"port", "volts", "wave"}) for a sequence plan. Times are counted from the first rising
edge of --from (e.g. the chip's reset release, the moment the rails are up in the sequence test), else from the start
of the dump. Only the VCD text is read.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaaval_engine import vcd  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vcd")
    ap.add_argument("signal")
    ap.add_argument("port")
    ap.add_argument("--volts", type=float, default=1.8)
    ap.add_argument("--invert", action="store_true", help="the analog pin is the inverse of the signal")
    ap.add_argument("--from", dest="origin", help="count time from this signal's first rising edge")
    a = ap.parse_args()
    sig = vcd.parse(open(a.vcd, errors="replace").read())
    name = vcd.find(sig, a.signal)
    if not name:
        sys.exit(f"{a.signal!r}: no single match among {len(sig)} signals (give more of its path)")
    t0 = 0.0
    if a.origin:
        o = vcd.find(sig, a.origin)
        if not o:
            sys.exit(f"--from {a.origin!r}: no single match (give more of its path, e.g. tb.{a.origin})")
        rise = [t for t, b in vcd.wave(sig[o]) if b == 1]
        if not rise:
            sys.exit(f"--from {o}: no rising edge")
        t0 = rise[0]
    w = [[max(0.0, t - t0), b] for t, b in vcd.wave(sig[name], invert=a.invert)]
    print(json.dumps(dict(port=a.port, volts=a.volts, wave=w, source=f"{os.path.basename(a.vcd)}:{name}")))


if __name__ == "__main__":
    main()

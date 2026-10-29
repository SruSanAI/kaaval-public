"""make_chip_demo.py — the landing page's chip-context figure (app/static/chip.json), from real simulations.

Two circuits of our own, the same ones the tests prove (tests/test_kaaval_sequence.py, tests/test_kaaval_logic.py):
  rails  a reference on the 1.8 V rail whose only start-up is a kick from the 3.3 V rail, in every rail order and speed
  logic  a kick-started reference whose power-down pin is released by our own logic (tests/data/en_release.vcd)
Every case, condition, state, current, schedule and finding on the page is written here from ngspice + sky130.

    python tools/make_chip_demo.py
"""
import json, os, sys, tempfile, pathlib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
from kaaval_engine import plan as P  # noqa: E402
import test_kaaval_logic as L  # noqa: E402
import test_kaaval_sequence as S  # noqa: E402


def scenario(pl, circuit_text, file_name):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / file_name).write_text(circuit_text)
    pl = dict(pl, corners=["tt", "ss", "ff"], temps=[27], vscales=[1.0])
    r = P.run(pl, str(d))
    assert r["ok"], r
    rows = []
    for name, sched, meta in P.cases(pl):
        cells = {x["corner"]: dict(state=x.get("state"), i_end=x.get("i_end"), error=x.get("error"))
                 for x in r["results"] if x["case"] == name}
        rows.append(dict(name=name, meta=meta, schedule={k: list(v) if v[0] != "wave" else ["wave", v[1]]
                                                         for k, v in sched.items()}, cells=cells))
    return dict(supplies=pl["supplies"], controls=[c["port"] for c in pl.get("controls") or []],
                rows=rows, findings=[dict(rule=f["rule"], message=f["message"], case=f.get("case"),
                                          sequence=f.get("sequence")) for f in r["findings"]])


def main():
    rails = scenario(S.plan(), S.CORE.format(startup=S.KICK), "ref.spice")
    logic = scenario(L.plan(L.logic_wave()), L.CORE.format(startup=L.KICK), "ref.spice")
    out = os.path.join(HERE, "app", "static", "chip.json")
    json.dump(dict(rails=rails, logic=logic, note="ngspice + sky130, our own circuits; tt/ss/ff at 27 °C"),
              open(out, "w"), separators=(",", ":"))
    for k, s in (("rails", rails), ("logic", logic)):
        print(k, len(s["rows"]), "cases", [f["rule"] for f in s["findings"]])
        for f in s["findings"]:
            print("  ", f["message"][:300])


if __name__ == "__main__":
    main()

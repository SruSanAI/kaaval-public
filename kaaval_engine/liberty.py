"""liberty.py — a timing model (Liberty .lib) for an analog cell, measured in ngspice, so digital timing tools see it.

Static timing analysis (OpenSTA, OpenROAD) times every path between flip-flops from Liberty models of the cells on it.
An analog macro has none, so the paths through the digital-analog boundary (a comparator output into a flip-flop, an
enable into a bias block) are never timed. This module characterises the cell the way standard cells are: for each
timing arc (input pin -> output pin) at each corner, an input edge of each slew drives the cell while the output
carries each load, and ngspice measures

  delay        input crossing 50 % to output crossing 50 % (cell_rise / cell_fall)
  transition   output 20 % -> 80 % (rise_transition / fall_transition)
  capacitance  input pin charge over a full swing, Q / V

The cell is the designer's own circuit; the engine builds every deck, nothing in the repository is run.

    lib = characterise(circuit, "comp", ports, supplies={"vdd": 1.8}, grounds=["vss"],
                       arcs=[("inp", "out")], biases={"inn": 0.9}, corner="tt")
    open("comp_tt.lib", "w").write(lib["text"])
"""
import re

from kaaval_engine import sim

SLEWS = [0.05e-9, 0.5e-9]            # input transition times (s), 20-80 %
LOADS = [2e-15, 20e-15]              # output loads (F)


def _deck_body(circuit, cell, ports, supplies, grounds, biases, arc, slew, load, vdd, settle):
    a, z = arc
    full = slew / 0.6                                 # 20-80 % slew -> 0-100 % ramp
    t1, t2 = settle, settle + 4 * settle
    lines = [circuit, f"Xcell {' '.join(ports)} {cell}"]
    for i, (p, v) in enumerate(supplies.items()):
        lines.append(f"Vsup{i} {p} 0 {v:.6g}")
    for i, g in enumerate(grounds):
        lines.append(f"Vgnd{i} {g} 0 0")
    for i, (p, v) in enumerate(biases.items()):
        lines.append(f"Vbias{i} {p} 0 {v:.6g}")
    lines.append(f"Vin {a} 0 PWL(0 0 {t1:.6g} 0 {t1 + full:.6g} {vdd:.6g} {t2:.6g} {vdd:.6g} {t2 + full:.6g} 0)")
    lines.append(f"Cload {z} 0 {load:.6g}")
    return "\n".join(lines), t1, t2, full


def _measure(circuit, cell, ports, supplies, grounds, biases, arc, slew, load, corner, temp, vdd, settle):
    a, z = arc
    body, t1, t2, full = _deck_body(circuit, cell, ports, supplies, grounds, biases, arc, slew, load, vdd, settle)
    tb = sim.Testbench(sch=f"{cell}.lib.sch", circuit=body, analyses=[".op"])
    tb.supplies = lambda: [(f"Vsup{i}", p, v) for i, (p, v) in enumerate(supplies.items())]
    stop = t2 + 4 * settle
    h, lo, hi = vdd / 2, 0.2 * vdd, 0.8 * vdd
    ctl = [f"option temp={temp}", f"tran {min(settle, full) / 50:.4g} {stop:.4g} 0 {min(settle, full) / 20:.4g}",
           f"meas tran vz0 avg v({z}) from={0.8 * t1:.4g} to={t1:.4g}",
           f"meas tran vz1 avg v({z}) from={t2 - 0.2 * settle:.4g} to={t2:.4g}",
           # input rises at t1, falls at t2; the output answers each edge in one direction
           f"meas tran d1 trig v({a}) val={h:.4g} rise=1 targ v({z}) val={h:.4g} cross=1 from={t1:.4g}",
           f"meas tran d2 trig v({a}) val={h:.4g} fall=1 targ v({z}) val={h:.4g} cross=2",
           f"meas tran r1 trig v({z}) val={lo:.4g} rise=1 targ v({z}) val={hi:.4g} rise=1",
           f"meas tran f1 trig v({z}) val={hi:.4g} fall=1 targ v({z}) val={lo:.4g} fall=1",
           f"meas tran q integ i(vin) from={t1:.4g} to={t1 + full + settle:.4g}"]
    out, err = sim.run(sim.deck(tb, corner, temp, 1.0, control="\n".join(ctl)), timeout=300)
    if err:
        return None, err
    v = {}
    for k in ("vz0", "vz1", "d1", "d2", "r1", "f1", "q"):
        m = re.search(rf"^{k}\s*=\s*([-+0-9.eE]+)", out, re.M)
        v[k] = float(m.group(1)) if m else None
    if v["vz0"] is None or v["vz1"] is None or abs(v["vz1"] - v["vz0"]) < 0.5 * vdd:
        return None, f"{z} does not switch when {a} does (from {v['vz0']} V to {v['vz1']} V)"
    v["sense"] = "positive_unate" if v["vz1"] > v["vz0"] else "negative_unate"
    return v, None


def characterise(circuit, cell, ports, supplies, grounds, arcs, biases=None, corner="tt", temp=27, slews=SLEWS,
                 loads=LOADS, settle=20e-9):
    """{text: Liberty source, tables: {arc: {...}}, errors: [...]} for one corner. Rail of the arcs: the first supply."""
    biases = biases or {}
    vdd = next(iter(supplies.values()))
    tables, errors, caps = {}, [], {}
    for arc in arcs:
        grid = {}
        for s in slews:
            for c in loads:
                r, e = _measure(circuit, cell, ports, supplies, grounds, biases, arc, s, c, corner, temp, vdd, settle)
                if e:
                    errors.append(f"{arc[0]}->{arc[1]} slew {s * 1e9:g} ns load {c * 1e15:g} fF: {e}")
                    continue
                grid[(s, c)] = r
        if len(grid) == len(slews) * len(loads):
            tables[arc] = grid
            q = [abs(r["q"]) for r in grid.values() if r["q"] is not None]
            if q:                                   # Vin drives only the input pin: its charge is the pin's
                caps[arc[0]] = min(q) / vdd
    return dict(text=_liberty(cell, ports, supplies, grounds, tables, caps, corner, temp, vdd, slews, loads),
                tables={f"{a}->{z}": {f"{s}|{c}": r for (s, c), r in g.items()} for (a, z), g in tables.items()},
                errors=errors)


def _liberty(cell, ports, supplies, grounds, tables, caps, corner, temp, vdd, slews, loads):
    ns = lambda x: f"{x * 1e9:.5f}"
    pf = lambda x: f"{x * 1e12:.6f}"
    idx1 = ", ".join(ns(s) for s in slews)
    idx2 = ", ".join(pf(c) for c in loads)

    def table(kind, arc, key, sense_ok=True):
        rows = []
        for s in slews:
            rows.append('"' + ", ".join(ns(tables[arc][(s, c)][key] or 0.0) for c in loads) + '"')
        return (f"          {kind} (kaaval_{len(slews)}x{len(loads)}) {{\n            index_1 (\"{idx1}\");\n"
                f"            index_2 (\"{idx2}\");\n            values ({', '.join(rows)});\n          }}\n")

    ins = sorted({a for a, _ in tables} | set(caps))
    outs = sorted({z for _, z in tables})
    L = [f"/* {cell}: timing measured by Kaaval with ngspice and the open sky130 models, corner {corner}, {temp} C. */",
         f"library (kaaval_{cell}_{corner}) {{",
         '  delay_model : table_lookup;', '  time_unit : "1ns";', '  voltage_unit : "1V";', '  current_unit : "1uA";',
         '  capacitive_load_unit (1, pf);', '  pulling_resistance_unit : "1kohm";',
         f"  nom_process : 1.0;", f"  nom_temperature : {temp};", f"  nom_voltage : {vdd:g};",
         "  slew_lower_threshold_pct_rise : 20;", "  slew_upper_threshold_pct_rise : 80;",
         "  slew_lower_threshold_pct_fall : 20;", "  slew_upper_threshold_pct_fall : 80;",
         "  input_threshold_pct_rise : 50;", "  input_threshold_pct_fall : 50;",
         "  output_threshold_pct_rise : 50;", "  output_threshold_pct_fall : 50;",
         f"  lu_table_template (kaaval_{len(slews)}x{len(loads)}) {{",
         "    variable_1 : input_net_transition;", "    variable_2 : total_output_net_capacitance;",
         f"    index_1 (\"{idx1}\");", f"    index_2 (\"{idx2}\");", "  }",
         f"  cell ({cell}) {{", "    dont_touch : true;", "    dont_use : true;"]
    for p in ins:
        L += [f"    pin ({p}) {{", "      direction : input;", f"      capacitance : {pf(caps.get(p, 0.0))};", "    }"]
    for z in outs:
        L += [f"    pin ({z}) {{", "      direction : output;"]
        for (a, zz), g in tables.items():
            if zz != z:
                continue
            first = next(iter(g.values()))
            sense = first["sense"]
            # positive unate: input rise -> output rise (d1 is the rise delay); negative: input rise -> output fall
            rise_d, fall_d = ("d1", "d2") if sense == "positive_unate" else ("d2", "d1")
            L += [f"      timing () {{", f"        related_pin : \"{a}\";", f"        timing_sense : {sense};",
                  table("cell_rise", (a, z), rise_d).rstrip("\n"), table("cell_fall", (a, z), fall_d).rstrip("\n"),
                  table("rise_transition", (a, z), "r1").rstrip("\n"),
                  table("fall_transition", (a, z), "f1").rstrip("\n"), "      }"]
        L.append("    }")
    L += ["  }", "}"]
    return "\n".join(L) + "\n"

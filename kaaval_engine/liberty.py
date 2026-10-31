"""liberty.py — a timing model (Liberty .lib) for an analog cell, measured in ngspice, so digital timing tools see it.

Static timing analysis (OpenSTA, OpenROAD) times every path between flip-flops from Liberty models of the cells on it.
An analog macro has none, so the paths through the digital-analog boundary (a comparator output into a flip-flop, an
enable into a bias block) are never timed. This module characterises the cell the way standard cells are: for each
timing arc (input pin -> output pin) at each corner, an input edge of each slew drives the cell while the output
carries each load, and ngspice measures

  delay        input crossing 50 % to output crossing 50 % (cell_rise / cell_fall)
  transition   output 20 % -> 80 % (rise_transition / fall_transition)
  capacitance  input pin charge over a full swing, Q / V

A clocked comparator is timed like a flip-flop: an arc ("clk", "out", "rising_edge") is clock -> output, written with
timing_type rising_edge and only the edge the decision makes. Its delay is not one number: the smaller the input
difference, the longer the latch takes to decide (and near zero it does not decide in time: metastability), so
decision_times() measures it against the overdrive, and the .lib is characterised at the smallest overdrive the design
must resolve (half an LSB for an ADC), which is stated in the library's comment. offset_check() first asks whether the
comparator resolves that overdrive at all with device mismatch: a decision time at 1 mV means nothing when the
mismatch offset is 10 mV.

The cell is the designer's own circuit; the engine builds every deck, nothing in the repository is run.

    lib = characterise(circuit, "comp", ports, supplies={"vdd": 1.8}, grounds=["vss"],
                       arcs=[("inp", "out")], biases={"inn": 0.9}, corner="tt")
    open("comp_tt.lib", "w").write(lib["text"])
"""
import re

from kaaval_engine import sim

SLEWS = [0.05e-9, 0.5e-9]            # input transition times (s), 20-80 %
LOADS = [2e-15, 20e-15]              # output loads (F)
MAX_WRONG = 0.05                     # a clock arc's .lib is refused when more mismatch samples decide wrong than this


def _deck_body(circuit, cell, ports, supplies, grounds, biases, arc, slew, load, vdd, settle):
    a, z = arc[:2]
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


def _measure(circuit, cell, ports, supplies, grounds, biases, arc, slew, load, corner, temp, vdd, settle, seed=None):
    a, z = arc[:2]
    body, t1, t2, full = _deck_body(circuit, cell, ports, supplies, grounds, biases, arc, slew, load, vdd, settle)
    tb = sim.Testbench(sch=f"{cell}.lib.sch", circuit=body, analyses=[".op"])
    tb.supplies = lambda: [(f"Vsup{i}", p, v) for i, (p, v) in enumerate(supplies.items())]
    stop = t2 + 4 * settle
    h, lo, hi = vdd / 2, 0.2 * vdd, 0.8 * vdd
    ctl = ([f"setseed {int(seed)}"] if seed is not None else []) + [   # a mismatch sample (corner *_mm) per seed
           f"option temp={temp}", f"tran {min(settle, full) / 50:.4g} {stop:.4g} 0 {min(settle, full) / 20:.4g}",
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


def decision_times(circuit, cell, ports, supplies, grounds, clk, out, inp, inn, vcm, overdrives=(0.1, 0.01, 0.001),
                   others=None, corner="tt", temp=27, slew=SLEWS[0], load=LOADS[0], settle=20e-9):
    """A clocked comparator's clock -> output delay at each input difference (V, inp above inn): [(overdrive, delay s or
    None, error)]. The delay grows as the difference shrinks; the smallest one the design must resolve is the one its
    timing model must use."""
    vdd = next(iter(supplies.values()))
    out_rows = []
    for dv in overdrives:
        b = dict(others or {}, **{inp: vcm + dv / 2, inn: vcm - dv / 2})
        r, e = _measure(circuit, cell, ports, supplies, grounds, b, (clk, out), slew, load, corner, temp, vdd, settle)
        out_rows.append((dv, (r or {}).get("d1"), e))
    return out_rows


def offset_check(circuit, cell, ports, supplies, grounds, clk, out, inp, inn, vcm, overdrive, samples=40, others=None,
                 corner="tt", temp=27, slew=SLEWS[0], load=LOADS[0], settle=20e-9):
    """Does a clocked comparator still decide the right way at +-overdrive with device mismatch? Each sample is one run
    at the PDK's mismatch corner (sky130 `<corner>_mm`: every device drawn on its own) with its own seed; a sample is
    wrong when the output does not rise at +overdrive or rises at -overdrive. Its timing model is only meaningful at
    an overdrive it resolves: write the .lib at the smallest one where (almost) no sample is wrong.
    -> {wrong, samples, errors, rate, rate_hi (95 % Wilson upper bound), overdrive, corner}"""
    vdd = next(iter(supplies.values()))
    mm = corner if corner.endswith("_mm") else f"{corner}_mm"
    wrong = errors = 0
    for seed in range(1, samples + 1):
        got = []
        for dv in (overdrive, -overdrive):
            b = dict(others or {}, **{inp: vcm + dv / 2, inn: vcm - dv / 2})
            r, e = _measure(circuit, cell, ports, supplies, grounds, b, (clk, out), slew, load, mm, temp, vdd, settle,
                            seed=seed)
            got.append(True if r is not None and r.get("vz1", 0) > r.get("vz0", 0)
                       else False if e and "does not switch" in e else None)
        if None in got:
            errors += 1
            continue
        wrong += (not got[0]) or got[1]
    n = samples - errors
    z = 1.96
    hi = 1.0 if n == 0 else min(1.0, ((wrong / n) + z * z / (2 * n) + z * ((wrong / n) * (1 - wrong / n) / n
                                                                           + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n))
    return dict(wrong=wrong, samples=n, errors=errors, rate=(wrong / n if n else None), rate_hi=hi,
                overdrive=overdrive, corner=mm)


def offset_gate(offset, clocked=True):
    """Should a comparator's .lib be written at this overdrive? offset is offset_check()'s result at the overdrive the
    model is characterised at. -> (ok, sentence for the library comment). Refused when more than MAX_WRONG of the
    mismatch samples decide the wrong way; written with a warning when too few samples ran to show the rate is low."""
    if not clocked:
        return True, ""
    if not offset:
        return True, "Offset with mismatch not checked: the delays assume the comparator decides the right way."
    od, n, wrong = offset["overdrive"] * 1e3, offset["samples"], offset["wrong"]
    if not n:
        return False, f"Offset check at +-{od:g} mV ran no samples ({offset['errors']} failed): not written."
    said = f"{wrong} of {n} mismatch samples ({offset['corner']}) decided the wrong way at +-{od:g} mV"
    if offset["rate"] > MAX_WRONG:
        return False, f"{said}: the comparator does not resolve this overdrive, so its delay here means nothing."
    if offset["rate_hi"] > MAX_WRONG:
        return True, f"{said}; with {n} samples up to {offset['rate_hi'] * 100:.0f} % may be wrong (95 % bound)."
    return True, f"{said}."


def characterise(circuit, cell, ports, supplies, grounds, arcs, biases=None, corner="tt", temp=27, slews=SLEWS,
                 loads=LOADS, settle=20e-9, note="", offset=None):
    """{text: Liberty source, tables: {arc: {...}}, errors: [...]} for one corner. Rail of the arcs: the first supply.
    A clock arc (a clocked comparator) passes offset_gate() first: offset is offset_check()'s result at the overdrive
    in biases; when the gate refuses, text is None and nothing is simulated."""
    biases = biases or {}
    ok, said = offset_gate(offset, clocked=any(len(a) > 2 for a in arcs))
    if not ok:
        return dict(text=None, tables={}, errors=[said])
    note = " ".join(x for x in (note, said) if x)
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
    return dict(text=_liberty(cell, ports, supplies, grounds, tables, caps, corner, temp, vdd, slews, loads, note),
                tables={f"{k[0]}->{k[1]}": {f"{s}|{c}": r for (s, c), r in g.items()} for k, g in tables.items()},
                errors=errors)


def _liberty(cell, ports, supplies, grounds, tables, caps, corner, temp, vdd, slews, loads, note=""):
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

    ins = sorted({k[0] for k in tables} | set(caps))
    outs = sorted({k[1] for k in tables})
    clocks = {k[0] for k in tables if len(k) > 2}
    L = [f"/* {cell}: timing measured by Kaaval with ngspice and the open sky130 models, corner {corner}, {temp} C."
         + (f" {note}" if note else "") + " */",
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
        L += [f"    pin ({p}) {{", "      direction : input;"] + (["      clock : true;"] if p in clocks else []) + \
             [f"      capacitance : {pf(caps.get(p, 0.0))};", "    }"]
    for z in outs:
        L += [f"    pin ({z}) {{", "      direction : output;"]
        for k, g in tables.items():
            a, zz = k[:2]
            if zz != z:
                continue
            first = next(iter(g.values()))
            sense = first["sense"]
            if len(k) > 2:
                # clock -> output: only the edge the decision makes (clock rise -> output leaves its reset level);
                # the reset on the falling clock is not a data path
                d, tr = ("d1", "r1") if sense == "positive_unate" else ("d1", "f1")
                L += [f"      timing () {{", f"        related_pin : \"{a}\";", f"        timing_type : {k[2]};",
                      table("cell_rise" if tr == "r1" else "cell_fall", k, d).rstrip("\n"),
                      table("rise_transition" if tr == "r1" else "fall_transition", k, tr).rstrip("\n"), "      }"]
                continue
            # positive unate: input rise -> output rise (d1 is the rise delay); negative: input rise -> output fall
            rise_d, fall_d = ("d1", "d2") if sense == "positive_unate" else ("d2", "d1")
            L += [f"      timing () {{", f"        related_pin : \"{a}\";", f"        timing_sense : {sense};",
                  table("cell_rise", (a, z), rise_d).rstrip("\n"), table("cell_fall", (a, z), fall_d).rstrip("\n"),
                  table("rise_transition", (a, z), "r1").rstrip("\n"),
                  table("fall_transition", (a, z), "f1").rstrip("\n"), "      }"]
        L.append("    }")
    L += ["  }", "}"]
    return "\n".join(L) + "\n"

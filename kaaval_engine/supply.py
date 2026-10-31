"""supply.py — the supply an on-chip regulator really gives the logic, as the timing corner to sign off at.

Static timing of the digital side uses standard-cell libraries characterised at one supply each (sky130_fd_sc_hd:
ss at 1.28-1.76 V, tt 1.80 V, ff 1.56-1.95 V). When the logic runs from the design's own LDO, the right library is
not the nominal 1.80 V one: setup must be checked at the slowest corner with the LOWEST voltage the LDO delivers,
hold at the fastest corner with the HIGHEST. This module measures the regulator's output (DC operating point) at each
condition and at the lightest and heaviest load current the logic draws, then names

  setup   the ss library at or just below the LDO's lowest output at ss (closest temperature)
  hold    the ff library at or just above its highest output at ff

so OpenSTA / OpenROAD time the logic at the supply it will actually see. With step=(i_lo, i_hi) the load also steps at
every ss condition (droop()): the lowest dip names the setup library for the moment the logic's current jumps.

The regulator is the designer's own circuit; the engine builds every deck, nothing in the repository is run.
"""
import re

from kaaval_engine import checks, sim

# sky130_fd_sc_hd Liberty corners (open_pdks): (process, temperature °C, supply V)
HD_LIBS = [("ss", 100, 1.40), ("ss", 100, 1.60), ("ss", -40, 1.28), ("ss", -40, 1.35), ("ss", -40, 1.40),
           ("ss", -40, 1.44), ("ss", -40, 1.60), ("ss", -40, 1.76), ("tt", 25, 1.80), ("tt", 100, 1.80),
           ("ff", 100, 1.65), ("ff", 100, 1.95), ("ff", -40, 1.56), ("ff", -40, 1.65), ("ff", -40, 1.76),
           ("ff", -40, 1.95)]


def lib_name(p, t, v):
    return f"sky130_fd_sc_hd__{p}_{'n40C' if t < 0 else f'{t:03d}C'}_{f'{v:.2f}'.replace('.', 'v')}"


def measure(circuit, cell, ports, supplies, grounds, out, load, biases=None, corner="tt", temp=27, vscale=1.0):
    """The regulator's output (V) at one condition with `load` amps drawn from `out` → (volts, None) or (None, why)."""
    lines = [circuit, f"Xcell {' '.join(ports)} {cell}"]
    for i, (p, v) in enumerate(supplies.items()):
        lines.append(f"Vsup{i} {p} 0 {v * vscale:.6g}")
    for i, g in enumerate(grounds):
        lines.append(f"Vgnd{i} {g} 0 0")
    for i, (p, v) in enumerate((biases or {}).items()):
        lines.append(f"Vbias{i} {p} 0 {v:.6g}")
    # the logic's current, which fades out near 0 V (an ideal source would drag a dropped-out output below ground)
    lines.append(f"Bload {out} 0 I={load:.6g}*tanh(max(v({out}),0)/0.05)")
    tb = sim.Testbench(sch=f"{cell}.ldo.sch", circuit="\n".join(lines), analyses=[".op"])
    tb.supplies = lambda: []
    text, err = sim.run(sim.deck(tb, corner, temp, 1.0, control=f"option temp={temp}\nop\nprint v({out})"), timeout=120)
    if err:
        return None, err
    m = re.search(rf"^v\({re.escape(out)}\)\s*=\s*([-+0-9.eE]+)", text, re.M | re.I)
    if not m:
        return None, "no operating point (the regulator did not converge)"
    return float(m.group(1)), None


def droop(circuit, cell, ports, supplies, grounds, out, i_lo, i_hi, biases=None, corner="tt", temp=27, vscale=1.0,
          edge=10e-9, settle=20e-6, hold=20e-6):
    """A load step from i_lo to i_hi (rising in `edge`) after the regulator has settled at i_lo: → ({before, low,
    after, droop}, None) or (None, why). low is the lowest output after the step (the supply the logic sees at that
    moment), after its settled value at i_hi."""
    lines = [circuit, f"Xcell {' '.join(ports)} {cell}"]
    for i, (p, v) in enumerate(supplies.items()):
        lines.append(f"Vsup{i} {p} 0 {v * vscale:.6g}")
    for i, g in enumerate(grounds):
        lines.append(f"Vgnd{i} {g} 0 0")
    for i, (p, v) in enumerate((biases or {}).items()):
        lines.append(f"Vbias{i} {p} 0 {v:.6g}")
    t1 = settle
    lines.append(f"Bload {out} 0 I=pwl(time, 0, {i_lo:.6g}, {t1:.6g}, {i_lo:.6g}, {t1 + edge:.6g}, {i_hi:.6g}, "
                 f"{t1 + hold + edge:.6g}, {i_hi:.6g})*tanh(max(v({out}),0)/0.05)")
    tb = sim.Testbench(sch=f"{cell}.ldo.sch", circuit="\n".join(lines), analyses=[".tran"])
    tb.supplies = lambda: []
    stop = t1 + edge + hold
    step = min(edge / 5, hold / 2000)
    ctl = [f"option temp={temp}", f"tran {step:.4g} {stop:.4g} 0 {step:.4g}",
           f"meas tran before avg v({out}) from={0.8 * t1:.4g} to={t1:.4g}",
           f"meas tran low min v({out}) from={t1:.4g} to={stop:.4g}",
           f"meas tran after avg v({out}) from={stop - 0.1 * hold:.4g} to={stop:.4g}"]
    text, err = sim.run(sim.deck(tb, corner, temp, 1.0, control="\n".join(ctl)),
                        timeout=300)
    if err:
        return None, err
    v = {}
    for k in ("before", "low", "after"):
        m = re.search(rf"^{k}\s*=\s*([-+0-9.eE]+)", text, re.M)
        v[k] = float(m.group(1)) if m else None
    if None in v.values():
        return None, "the load-step transient did not finish"
    v["droop"] = v["before"] - v["low"]
    return v, None


def _ss_lib(volts, temp):
    libs = [x for x in HD_LIBS if x[0] == "ss" and x[2] <= volts + 1e-9]
    return lib_name(*max(libs, key=lambda x: (x[2], -abs(x[1] - temp)))) if libs else None


def corner(circuit, cell, ports, supplies, grounds, out, loads, biases=None, corners=None, temps=None, vscales=None,
           step=None):
    """{rows: [(corner, temp, vscale, load, volts or None, error)], setup: {...}, hold: {...}, errors: [...]}.
    step=(i_lo, i_hi): also the load step at every ss condition → setup_step, the library for the lowest dip."""
    corners, temps, vscales = corners or checks.CORNERS, temps or checks.TEMPS, vscales or checks.VSCALES
    rows, errors = [], []
    for c in corners:
        for t in temps:
            for s in vscales:
                for i in loads:
                    v, e = measure(circuit, cell, ports, supplies, grounds, out, i, biases, c, t, s)
                    rows.append((c, t, s, i, v, e))
                    if e:
                        errors.append(f"{c} {t} °C {s:g}× {i * 1e3:g} mA: {e}")
    ok = [r for r in rows if r[4] is not None]
    out_ = dict(rows=rows, errors=errors, setup=None, hold=None)
    ss = [r for r in ok if r[0] == "ss"] or ok
    ff = [r for r in ok if r[0] == "ff"] or ok
    if ss:
        lo = min(ss, key=lambda r: r[4])
        libs = [x for x in HD_LIBS if x[0] == "ss" and x[2] <= lo[4] + 1e-9]
        pick = max(libs, key=lambda x: (x[2], -abs(x[1] - lo[1]))) if libs else None
        out_["setup"] = dict(volts=lo[4], at=lo[:4], lib=lib_name(*pick) if pick else None,
                             note=None if pick else f"{lo[4]:.3f} V is below every ss library (lowest 1.28 V): "
                                                     "characterise the cells at this supply")
    if ff:
        hi = max(ff, key=lambda r: r[4])
        libs = [x for x in HD_LIBS if x[0] == "ff" and x[2] >= hi[4] - 1e-9]
        pick = min(libs, key=lambda x: (x[2], abs(x[1] - hi[1]))) if libs else None
        out_["hold"] = dict(volts=hi[4], at=hi[:4], lib=lib_name(*pick) if pick else None,
                            note=None if pick else f"{hi[4]:.3f} V is above every ff library (highest 1.95 V)")
    if step:
        dips = []
        for t_ in temps:
            for s in vscales:
                if "ss" in corners:
                    d, e = droop(circuit, cell, ports, supplies, grounds, out, step[0], step[1], biases, "ss", t_, s)
                    if e:
                        errors.append(f"ss {t_} °C {s:g}× load step: {e}")
                    else:
                        dips.append((d, t_, s))
        if dips:
            d, t_, s = min(dips, key=lambda x: x[0]["low"])
            lib = _ss_lib(d["low"], t_)
            out_["setup_step"] = dict(volts=d["low"], droop=d["droop"], at=("ss", t_, s, step), lib=lib,
                                      note=None if lib else f"{d['low']:.3f} V is below every ss library (lowest "
                                                            "1.28 V): characterise the cells at this supply")
    return out_


def sta_note(r):
    """What to tell OpenSTA, as comment lines a designer can paste next to their read_liberty."""
    lines = ["# Kaaval: the logic's supply comes from the design's regulator (DC, measured in ngspice)."]
    for k, what in (("setup", "lowest"), ("hold", "highest")):
        s = r.get(k)
        if not s:
            continue
        c, t, v, i = s["at"]
        lines.append(f"# {k}: {what} output {s['volts']:.3f} V at {c} {t} °C {v:g}× input, {i * 1e3:g} mA load")
        lines.append(f"#   read_liberty $::env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/lib/{s['lib']}.lib"
                     if s["lib"] else f"#   {s['note']}")
    st = r.get("setup_step")
    if st:
        c, t, v, (lo, hi) = st["at"]
        lines.append(f"# setup with a load step {lo * 1e3:g} -> {hi * 1e3:g} mA: dips {st['droop'] * 1e3:.0f} mV to "
                     f"{st['volts']:.3f} V at {c} {t} °C {v:g}× input")
        lines.append(f"#   read_liberty $::env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/lib/{st['lib']}.lib"
                     if st["lib"] else f"#   {st['note']}")
    else:
        lines.append("# A load step droops below the DC value: check the transient droop before taking less margin.")
    return "\n".join(lines) + "\n"

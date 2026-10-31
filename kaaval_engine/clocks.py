"""clocks.py — an on-chip oscillator's clock, measured in ngspice, as constraints digital timing tools read (SDC).

An oscillator has no clock input: it runs from its supply (and a control voltage, for a VCO), so the clock it gives
the digital side moves with process, temperature and supply. Static timing (OpenSTA, OpenROAD) needs that clock as
`create_clock` on the oscillator's output pin, with its period and duty cycle. This module powers the cell up at each
condition, lets it run, and measures over several cycles

  period       rising crossing to the next rising crossing of the output at half the supply
  high time    rising crossing to the following falling crossing (duty = high / period)
  swing        the output's lowest and highest level (a clock that does not reach both rails is not a clock yet)

and writes one SDC per process corner (the shortest period of that corner over its temperatures and supplies: the
fastest the clock runs while the logic is timed with that corner's libraries) and one conservative SDC (the shortest
period anywhere). Duty cycle goes into -waveform. Jitter is NOT measured: a noiseless transient has none, so the SDC
leaves set_clock_uncertainty to the designer's jitter budget (or writes it when one is given).

The cell is the designer's own circuit; the engine builds every deck, nothing in the repository is run.

    r = constraints(circuit, "ring5", ["out", "vdd", "vss"], {"vdd": 1.8}, ["vss"], "out", pin="u_osc/out")
    open("osc_ss.sdc", "w").write(r["sdc"]["ss"])
"""
import re

from kaaval_engine import checks, sim


def _deck(circuit, cell, ports, supplies, grounds, biases, out, vscale, ramp, tmax, step):
    lines = [circuit, f"Xcell {' '.join(ports)} {cell}"]
    for i, (p, v) in enumerate(supplies.items()):         # a supply ramp starts the oscillation
        lines.append(f"Vsup{i} {p} 0 PWL(0 0 {ramp:.4g} {v * vscale:.6g})")
    for i, g in enumerate(grounds):
        lines.append(f"Vgnd{i} {g} 0 0")
    for i, (p, v) in enumerate((biases or {}).items()):
        lines.append(f"Vbias{i} {p} 0 {v:.6g}")
    return "\n".join(lines)


def measure(circuit, cell, ports, supplies, grounds, out, biases=None, corner="tt", temp=27, vscale=1.0,
            tmax=50e-9, cycles=8, ramp=1e-9, load=5e-15):
    """One condition → ({period, high, duty, vmin, vmax, n}, None) or (None, why)."""
    vdd = next(iter(supplies.values())) * vscale
    h = vdd / 2
    body = _deck(circuit, cell, ports, supplies, grounds, biases, out, vscale, ramp, tmax, None)
    body += f"\nCload {out} 0 {load:.6g}"
    tb = sim.Testbench(sch=f"{cell}.osc.sch", circuit=body, analyses=[".tran"])
    tb.supplies = lambda: []                               # supplies are scaled in the deck already
    step = tmax / 20000
    ctl = [f"option temp={temp}", f"tran {step:.4g} {tmax:.4g} 0 {step:.4g}",
           f"meas tran vmin min v({out}) from={tmax / 2:.4g} to={tmax:.4g}",
           f"meas tran vmax max v({out}) from={tmax / 2:.4g} to={tmax:.4g}"]
    # the last cycles before tmax: count crossings from half the run, when start-up is over
    for k in range(1, cycles + 2):
        ctl.append(f"meas tran r{k} when v({out})={h:.4g} rise={k} from={tmax / 2:.4g}")
        ctl.append(f"meas tran f{k} when v({out})={h:.4g} fall={k} from={tmax / 2:.4g}")
    text, err = sim.run(sim.deck(tb, corner, temp, 1.0, control="\n".join(ctl)), timeout=300)
    if err:
        return None, err
    v = {}
    for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", text, re.M):
        v[m.group(1).lower()] = float(m.group(2))
    lo, hi = v.get("vmin"), v.get("vmax")
    rises = [v[f"r{k}"] for k in range(1, cycles + 2) if f"r{k}" in v]
    falls = [v[f"f{k}"] for k in range(1, cycles + 2) if f"f{k}" in v]
    if len(rises) < 3:
        sw = f" (it swings {lo:.3g}–{hi:.3g} V)" if lo is not None and hi is not None else ""
        return None, f"{out} does not oscillate in the second half of {tmax * 1e9:g} ns{sw}"
    periods = [b - a for a, b in zip(rises, rises[1:])]
    highs = [next(f for f in falls if f > r) - r for r in rises[:-1] if any(f > r for f in falls)]
    period = sum(periods) / len(periods)
    high = sum(highs) / len(highs) if highs else None
    if lo is not None and hi is not None and (hi - lo) < 0.8 * vdd:
        return None, (f"{out} swings only {lo:.3g}–{hi:.3g} V of {vdd:.3g} V: not a rail-to-rail clock yet "
                      "(it needs a buffer or level shifter before the logic)")
    return dict(period=period, high=high, duty=(high / period if high else None), vmin=lo, vmax=hi,
                n=len(periods), spread=(max(periods) - min(periods)) / period), None


def constraints(circuit, cell, ports, supplies, grounds, out, biases=None, pin=None, name="osc_clk",
                corners=None, temps=None, vscales=None, jitter=None, tmax=50e-9, cycles=8):
    """All conditions → {rows: [(corner, temp, vscale, result or None, error)], sdc: {corner: text, "all": text},
    summary: {corner: {...}}, errors: [...]}."""
    corners, temps, vscales = corners or checks.CORNERS, temps or checks.TEMPS, vscales or checks.VSCALES
    rows, errors = [], []
    for c in corners:
        for t in temps:
            for s in vscales:
                r, e = measure(circuit, cell, ports, supplies, grounds, out, biases, c, t, s, tmax, cycles)
                rows.append((c, t, s, r, e))
                if e:
                    errors.append(f"{c} {t} °C {s:g}×: {e}")
    pin = pin or f"{cell}/{out}"
    summary, sdc = {}, {}
    ok = [x for x in rows if x[3]]
    for c in corners + ["all"]:
        mine = [x for x in ok if c == "all" or x[0] == c]
        if not mine:
            continue
        fast = min(mine, key=lambda x: x[3]["period"])
        slow = max(mine, key=lambda x: x[3]["period"])
        duties = [x[3]["duty"] for x in mine if x[3]["duty"]]
        n_all = sum(1 for x in rows if c == "all" or x[0] == c)
        summary[c] = dict(period=fast[3]["period"], at=fast[:3], slowest=slow[3]["period"], slow_at=slow[:3],
                          duty_lo=min(duties) if duties else None, duty_hi=max(duties) if duties else None,
                          measured=len(mine), of=n_all)
        sdc[c] = _sdc(cell, out, pin, name, c, summary[c], fast[3], jitter)
    return dict(rows=rows, sdc=sdc, summary=summary, errors=errors)


def _ns(x):
    return f"{x * 1e9:.4f}".rstrip("0").rstrip(".")


def _sdc(cell, out, pin, name, corner, s, fast, jitter):
    p = s["period"]
    high = p * (fast["duty"] or 0.5)
    where = "every corner" if corner == "all" else f"corner {corner}"
    lines = [f"# Kaaval: clock from {cell} output {out}, measured in ngspice (sky130), {where}.",
             f"# Period {_ns(p)} ns at {s['at'][0]} {s['at'][1]} °C {s['at'][2]:g}× supply (the fastest), "
             f"up to {_ns(s['slowest'])} ns at {s['slow_at'][0]} {s['slow_at'][1]} °C {s['slow_at'][2]:g}×.",
             f"# Duty cycle {100 * s['duty_lo']:.1f}–{100 * s['duty_hi']:.1f} %; measured at {s['measured']} of "
             f"{s['of']} conditions." if s["duty_lo"] else f"# Measured at {s['measured']} of {s['of']} conditions.",
             f"create_clock -name {name} -period {_ns(p)} -waveform {{0 {_ns(high)}}} [get_pins {{{pin}}}]"]
    if jitter:
        lines.append(f"set_clock_uncertainty {_ns(jitter)} [get_clocks {{{name}}}]")
    else:
        lines.append("# Jitter is not measured (a noiseless transient has none): add the jitter budget with")
        lines.append(f"#   set_clock_uncertainty <ns> [get_clocks {{{name}}}]")
    return "\n".join(lines) + "\n"


# ── PLL lock time: how long the logic's reset must hold ─────────────────────────────────────────────────────────────
def pll_lock(circuit, cell, ports, supplies, grounds, ref, f_ref, ctrl, fb=None, biases=None, corner="tt", temp=27,
             vscale=1.0, tmax=6e-6, windows=120, band=0.01):
    """A PLL powered up with its reference running: the time its control voltage `ctrl` settles for good, so a reset
    released earlier lets the logic run on a clock that is still moving. The control voltage is averaged over every
    reference period (the ripple of each phase comparison averages out); locked = the last moment that average
    leaves a band of `band` x supply (at least 5 mV) around its final value. With `fb` (the divided clock the PLL
    compares), its period at the end must equal the reference's: a loop that settles somewhere else has not locked.
    → ({lock, ctrl_final, fb_period, ref_period}, None) or (None, why)."""
    vdd = next(iter(supplies.values())) * vscale
    lines = [circuit, f"Xcell {' '.join(ports)} {cell}"]
    for i, (p, v) in enumerate(supplies.items()):
        lines.append(f"Vsup{i} {p} 0 PWL(0 0 50n {v * vscale:.6g})")
    for i, g in enumerate(grounds):
        lines.append(f"Vgnd{i} {g} 0 0")
    for i, (p, v) in enumerate((biases or {}).items()):
        lines.append(f"Vbias{i} {p} 0 {v:.6g}")
    tr = 1 / f_ref
    lines.append(f"Vref {ref} 0 PULSE(0 {vdd:.6g} 100n {tr / 50:.4g} {tr / 50:.4g} {tr / 2 - tr / 50:.4g} {tr:.6g})")
    tb = sim.Testbench(sch=f"{cell}.pll.sch", circuit="\n".join(lines), analyses=[".tran"])
    tb.supplies = lambda: []
    step = tr / 200
    t_on = 100e-9
    n = max(10, min(windows, int((tmax - t_on) / tr)))
    span = (tmax - t_on) / n
    ctl = [f"option temp={temp}", f"tran {step:.4g} {tmax:.4g} 0 {step:.4g}"]
    for k in range(n):
        a = t_on + k * span
        ctl.append(f"meas tran w{k} avg v({ctrl}) from={a:.6g} to={a + span:.6g}")
    if fb:
        h = vdd / 2
        ctl += [f"meas tran fa when v({fb})={h:.4g} rise=1 from={tmax - 12 * tr:.6g}",
                f"meas tran fz when v({fb})={h:.4g} rise=11 from={tmax - 12 * tr:.6g}"]
    text, err = sim.run(sim.deck(tb, corner, temp, 1.0, control="\n".join(ctl)), timeout=900)
    if err:
        return None, err
    vals = {}
    for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", text, re.M):
        vals[m.group(1).lower()] = float(m.group(2))
    w = [vals.get(f"w{k}") for k in range(n)]
    if any(x is None for x in w):
        return None, "the PLL transient did not finish"
    final = sum(w[-max(3, n // 20):]) / max(3, n // 20)
    tol = max(0.005, band * vdd)
    out_at = [k for k in range(n) if abs(w[k] - final) > tol]
    lock = t_on + (out_at[-1] + 1) * span if out_at else t_on
    r = dict(lock=lock, ctrl_final=final, ref_period=tr, settled_for=tmax - lock)
    if fb:
        fa, fz = vals.get("fa"), vals.get("fz")
        r["fb_period"] = (fz - fa) / 10 if fa is not None and fz is not None else None
        if r["fb_period"] is None or abs(r["fb_period"] - tr) > 0.01 * tr:
            return None, (f"{fb} does not run at the reference period at the end ({r['fb_period']} s vs {tr:.4g} s): "
                          "the loop has not locked")
    if r["settled_for"] < 0.2 * (tmax - t_on):
        return None, f"{ctrl} is still moving near the end of {tmax * 1e6:g} µs (not locked yet)"
    return r, None


def reset_check(lock, release):
    """The logic's reset released at `release` (s, from the project's own logic or the designer's bench) against the
    PLL's lock time → None (fine) or the finding text."""
    if release is None or lock is None or release >= lock:
        return None
    return (f"the reset lets go {release * 1e6:.2f} µs after power-up but the PLL locks only after {lock * 1e6:.2f} µs: "
            f"for {(lock - release) * 1e6:.2f} µs the logic runs on a clock that is still moving")

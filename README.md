<img src="assets/hero.svg" width="100%" alt="Kaaval, the senior reviewer your analog chip never had: Kaaval's own current reference, powered up from 0 V at 45 conditions, stays dead at 30 of them; the proposed start-up device makes it start at all 45. By Sanjay Sivakumar, signed SruSan.">

# Kaaval

**Kaaval** (Tamil காவல், "guard") reviews open-silicon analog chip designs the way a senior analog engineer would.
Paste a repository: Kaaval rebuilds every circuit from the schematics as text, **Muse Spark plans the tests the
designer never ran** (power-up from 0 V, loop stability, corners, and the block **in its chip context**: which rail
comes up first, how fast, when enables and resets are released, the load of the chip's pad), and the simulator proves
every finding at **5 process corners × 3 temperatures × 3 supplies**, before the fab finds it for you.

Why the chip context: an analog block is usually simulated alone, with every supply switched on together. On the chip,
rails come up in some order and at some speed, controls arrive late and the output drives a pad. Tiny Tapeout's
precheck runs no simulation, so nothing checks this before the fab.

Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026). Everything in this repository was written
during the event; see [What runs where](#what-runs-where).

## What it catches

| Failure in silicon | How Kaaval proves it | Measured on our own circuits |
|---|---|---|
| **It wakes up dead.** A self-biased reference has a second, 0 A solution. | Every source ramps from 0 V and is held; a dead state counts only when the supply current settles there. | Our beta-multiplier reference without a start-up device: **30 of 45 conditions stay at 0 µA** (DC analysis says 9.35 µA). With one weak start-up PMOS: **0 of 45**. |
| **It settles in the wrong state.** | The settled state is handed back to the DC solver; it counts only if the solver keeps it (a real second operating point). | Tests: a seeded reference without start-up caught at every condition; an inverter at its trip point (high gain, one state) correctly passes. |
| **It rings or never settles.** | The loop is cut where the planner says and loop gain is measured by double injection (Tian's method): phase margin, gain margin, unity-gain frequency at every condition. | Matches the exact return ratio of a test loop to the digit (UGF 8.894 MHz, PM 117.262°, GM 22.707 dB). Our two-stage op-amp: PM 68° → 44° → 21° as the load grows; step overshoot 0 % / 20 % / 45 % for PM 82° / 44° / 21°. |
| **It works only if the chip powers up in the right order.** A start-up that depends on another rail, or on a control pin. | Muse Spark labels each pin (supply, ground, enable, reset, output) and picks the sequences: every rail first in turn with the others 10 µs, 100 µs or 1 ms later; fast (2 µs) and slow (1 ms) ramps; controls with the rails or 20 µs after them. Outputs drive the pad path (500 Ω, 5 pF, 10 kΩ to ground). A failure is reported with the gap at which it starts failing and the largest gap that still passes, never one chosen gap. | Our reference on the 1.8 V rail kicked from the 3.3 V rail: starts with the rails together, **stays off when 3.3 V leads by 1 ms, starts at 100 µs**. With its own start-up device: passes every sequence. Enables and resets can also follow **the project's own logic**: a digital simulation's VCD gives the release time (`tools/logic_wave.py`). Our power-down pin, released by our counter 54.5 µs after the rail: the kick-started reference stays off (0.33 nA instead of 10.8 µA). |
| **It loses its margin at a corner.** | The designer's own testbench at all 45 conditions; every transistor's saturation margin and bias tracked, down to the sub-circuit it lives in. | 45 conditions in about 10 s per testbench. |
| **The simulation itself is wrong.** | Units audit: device sizes read as text, checked against what the silicon can be. | Found in 6 Tiny Tapeout repositories: diodes whose area reads as 1 m² under `.option scale`. |

Every number above comes from ngspice-47 with the open sky130 PDK. Kaaval is **pre-silicon simulation on open PDKs,
not foundry sign-off**; one measured run is not a guarantee.

## How a review works

1. **Read.** Schematics (xschem) and SPICE netlists are parsed as text and netlisted the way xschem would
   (94.8 % of 8,394 devices identical on 434 xschem-written netlists). Nothing in the repository is ever executed.
2. **Plan (Muse Spark).** Muse Spark reads the docs and every circuit cell, names each block and its risks, labels
   the job of every pin with its evidence, and writes test plans as JSON (a strict schema). Plans are data: the engine checks every cell, port and value before anything
   runs, and refuses raw SPICE. Without a Muse Spark key, a labelled no-model baseline powers up every circuit.
3. **Prove.** The engine builds every deck itself and simulates at all 45 conditions. A finding is shown only after
   its own confirmation (second states re-solved, oscillations re-run with a stiffer integrator).
4. **Fix.** A proposal, never a merge: a sizing fix is re-simulated at all 45 conditions before it is shown.

The review page shows the evidence behind each finding: the failing device on its own schematic sheet, the
conditions where it fails, a **sequence matrix** (every power-up order against every condition, click a cell for its
waveform), the **power-up waveform** of any condition (simulated on click), and the **Bode plot** of a
loop at every condition.

## Run it

Needs only open tools: [ngspice](https://ngspice.sourceforge.io/) and the open sky130 PDK.

    brew install ngspice                                   # or your distro's ngspice (tested with ngspice-47)
    pip install volare flask
    volare enable --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b
    KAAVAL_PORT=5110 python -m app.server                  # http://127.0.0.1:5110

Or as a container (ngspice, the pruned PDK and the app): `docker build -t kaaval . && docker run -p 7860:7860 kaaval`
(see [docs/HOSTING.md](docs/HOSTING.md)).

| Environment | Enables |
|---|---|
| `MUSE_API_KEY` | Muse Spark plans the review (Meta Model API) |
| `MINNAL_URL`, `MINNAL_KEY` | sizing fixes from Minnal (below) |
| `KAAVAL_MAX_REVIEWS` | reviews simulating at once (default 2; others wait) |
| `KAAVAL_ACCESS_CODE` | a code needed to start a review (for a public link) |
| `KAAVAL_REVIEWS_PER_HOUR`, `KAAVAL_MAX_WAITING` | per-visitor limit (default 4/hour) and queue cap (default 6) |

Tests (they simulate): `python tests/test_local_engine.py`, `tests/test_kaaval_startup.py`,
`tests/test_kaaval_stability.py`, `tests/test_kaaval_sequence.py`, `tests/test_kaaval_logic.py`, `tests/test_kaaval_stdcells.py`,
`tests/test_kaaval_spice_cells.py`, `tests/test_netlister.py`.

## What runs where

Written during the event and in this repository: the netlister, units audit, PVT engine, operating-point, power-up
and stability checks, power-up sequence and pad checks, standard-cell loading, test plans, SPICE-subcircuit cells, waveforms, the Muse Spark planner and the web app. It runs
on its own.

One optional feature uses **Minnal**, SruSan's private analog design product that existed before the event: the
sizing-fix search behind "Try a sizing fix". With `MINNAL_URL` and `MINNAL_KEY` set, the design's text files go to
Minnal's keyed engine API and its verified proposal comes back; without them every review still runs in full and the
button says the fix search is not connected. Minnal itself is not part of this submission.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) · [CHANGELOG.md](CHANGELOG.md) · security reports: [SECURITY.md](SECURITY.md) (never a
public issue) · [Code of Conduct](CODE_OF_CONDUCT.md)

## Limits

- Open PDKs only (sky130 today); foundry PDKs and commercial simulators are not supported.
- Schematic-level: layout parasitics are seen only when an extracted netlist is in the repository.
- Repositories with only images or PDFs of their schematics cannot be simulated; Kaaval says so.

---
by Sanjay Sivakumar · [github.com/SruSanCyborg](https://github.com/SruSanCyborg)

## Licence

MIT, see [LICENSE](LICENSE). Minnal is not included and is not under this licence.

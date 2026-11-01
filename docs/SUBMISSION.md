# Submission draft (Meta hackathon, due Thu 5 Nov 6:30 AM IST)

Everything below uses numbers already measured in the README. Lines marked **FILL** wait for a run that has not
happened yet. If a run does not happen, its line is dropped, not guessed.

## One line

Kaaval reviews open-silicon analog chip designs like a senior analog engineer: Muse Spark plans the tests the
designer never ran, and ngspice proves every finding at 45 conditions before the fab finds it.

## The problem (form: "what does it do")

An analog block is usually simulated alone, with every supply on at once. On the chip, rails come up in some order
and at some speed, enables and resets arrive late, and the output drives a pad. A circuit with two DC solutions can
pass every simulation its designer ran and still come up dead on silicon. Open-silicon shuttles check layout rules,
not this.

Kaaval takes a repository, rebuilds every circuit from its schematics as text (nothing in the repo is executed), and:

1. **Muse Spark plans:** it names each block and its risks, labels every pin's job with evidence, and writes test
   plans as JSON under a strict schema. The engine validates every cell, port and value, and refuses raw SPICE.
2. **ngspice proves:** at 5 process corners × 3 temperatures × 3 supplies. A finding is shown only after its own
   confirmation: a fine-step check, second states re-solved.
3. **A fix is proposed, never merged:** it is re-simulated at all 45 conditions before it is shown.

## Measured results (README)

- Our self-biased reference without a start-up device: **30 of 45 conditions stay at 0 µA**, while DC analysis
  reports a working bias at every one. With one weak start-up PMOS: 0 of 45.
- Loop gain by double injection matches the exact return ratio of a test loop to the digit (UGF 8.894 MHz,
  PM 117.262°).
- Power-up order: our reference kicked from the 3.3 V rail stays off when 3.3 V leads by 1 ms, and starts at 100 µs.
- Into the timing flow:
  - an SDC clock from a ring oscillator, 1.133–3.573 ns over the 45 conditions;
  - the LDO's load-step droop puts setup on `ss_n40C_1v35`, not `1v44`;
  - a StrongARM latch decides wrong in 30 of 40 mismatch samples at ±1 mV, so its `.lib` is refused there.
- Netlister: 95.3 % of 8,394 devices identical to xschem's own output, on 434 netlists.
- Symbols named by a bare name or by another machine's PDK path now resolve as xschem finds them: unresolved
  component references in the 98 cloned repositories fall from 4,603 to 98. The same holds for finding a
  schematic's ports and its testbenches: 139 schematics in 21 repositories get their ports, 86 testbenches in 10
  are found.
- A SPICE subcircuit's ports continued on `+` lines (Magic writes ten pins to a line) are read: 757 of 4,118 SPICE
  cells in 59 repositories had a truncated pin list, and 269 of them in 50 repositories now have their supply and
  ground pins, so the baseline can power them up.
- Layout against schematic (Magic + Netgen, transistor level, in every review): on 98 cloned Tiny Tapeout analog
  repositories, 451 cells drawn both ways, 274 match and 51 warnings fall in 26 repositories (different devices,
  or sizes more than 5 % off), median 0.18 s per cell. Counts only.
  7 cells in 7 repositories draw one of their pins in pieces that are not connected (Magic's `_uq` labels); 1 is a
  project's top cell, where nothing above joins them. 12 more are the same devices plus ideal schematic parts the
  layout cannot draw (ideal 10 fF ring loads, model-less R and C), now named instead of "not judged"; 6 match once
  the transistor bodies the layout leaves on a net of their own are tied as the schematic ties them (all sub-cells),
  4 once a pin drawn in pieces is joined. Not judged: 50 -> 28.
- As drawn, with its capacitance: a matched cell's own power-up / stability test re-runs on the layout extracted
  with its parasitic capacitance. Compared only when the test drives every input (in a pilot, all three
  differences of undriven tests were floating inputs): Muse Spark's biased plans are what it runs on.
- Big cells: a flash ADC power-up went from 30 of 30 conditions unconfirmed (753 s) to 3 of 30 (662 s) with the
  windowed fine-step check; full-length ground truth agrees to 6 digits.
- 45 conditions in 1.1-2.0 s for 6 of 8 sampled testbenches (50 / 124 s for the two largest).
- A review is bounded: planned tests share 600 s. The flash ADC's full review takes 610 s instead of 1,968 s with the
  same findings, and says that 72 of its 165 power-up conditions were not run (the old code ran one 1,366-device
  design for 20 h).
- Findings from a test that left an input undriven (stays off, undetermined start-up, weak output) are notes, not
  warnings. Checked against silicon outcomes first: in backtest v2 that moves 24 warnings on chips that work and
  none of the failures' own findings. Oscillation stays a warning.
- The no-model baseline chooses among the cells it can test before taking the largest: on the 28 backtest rows,
  cells powered up go from 59 to 74; an op-amp chip whose layout netlist's standard cells had taken every slot goes
  from 0 tested cells to 6.
- **FILL** silicon backtest: counts only, as `tools/score_backtest.py` prints them (rows, findings, unconfirmed, rails).
- **FILL** Muse arm vs rules arm (held-out ablation; pin roles, where the rules arm scores 143/189 = 76 %).

## Built during the event (startup-track label)

All of `SruSanAI/kaaval`, starting 27 Oct: the netlister, the engine, the planner, the review UI, chip view,
Silicon Twin, the timing outputs (`.lib`, SDC, supply corner), layout against schematic and post-layout re-runs,
the backtest tools.

Pre-existing and declared: Minnal, our private analog designer. Kaaval runs standalone without it. With
`MINNAL_URL`/`MINNAL_KEY` set, only the sizing-fix search is called on Minnal.

## Where Muse Spark is load-bearing

- Reading a repo's docs, schematics and schematic images into blocks, risks and pin roles. A rules baseline cannot
  place a stability cut, because that needs an understanding of the topology.
- Choosing the power-up sequences and chip-context tests per block.
- Explaining each proven finding in the designer's terms.

The no-model baseline is labelled as such in the UI.

## Video (3 min, real runs at 1×, no cuts inside a run)

| Time | Shot |
|---|---|
| 0:00–0:20 | Hero: the reference dead at 30 of 45 conditions, alive at 45 with the fix. One sentence of problem. |
| 0:20–0:50 | Upload our own demo tile (`examples/demo_tapeout`, a zip): Muse Spark's plan streams in: blocks, pin roles with evidence, tests chosen. |
| 0:50–1:30 | Proving: the 45-condition grid fills. A finding opens: failing device on its sheet, waveform on click. |
| 1:30–2:00 | Sequence matrix: rail order × condition. Click the 3.3 V-leads-by-1-ms cell: stays off. |
| 2:00–2:30 | Chip view, down to the transistor. Into the timing flow: SDC clock, supply corner, `.lib` refused at ±1 mV. |
| 2:30–2:50 | Fix proposed, re-simulated at 45 conditions. Download the ngspice deck a designer can run without Kaaval. |
| 2:50–3:00 | Repo link, "pre-silicon simulation on open PDKs, not foundry sign-off". |

Recording: `~/Downloads/minnal-film/recorder/record_kaaval.py` (headless Chromium, real clicks, 1×) drives this shot
list against a running Kaaval with the demo zip. Only our own design is reviewed on camera, so no one else's results
are shown.

## Checklist

- [ ] Muse preflight passes (docs/MUSE_READY.md, step 1)
- [ ] FILL lines above filled or dropped
- [ ] kaaval-public flipped to public (Sanjay)
- [ ] Live product URL (docs/HOSTING.md)
- [ ] Video recorded (real runs, 1×) and uploaded
- [ ] Form submitted before 5 Nov 6:30 AM IST

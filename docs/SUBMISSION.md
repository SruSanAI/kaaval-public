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
- Netlister, against netlists xschem itself wrote and committed: 95.5 % of 8,394 PDK devices identical (name,
  model, nets in pin order) on 434 netlists. Over every element drawn from a schematic (instances, sources, R, C):
  93.7 % of 20,211 connected identically with net names mapped one to one, 79.6 % with names literal (a wire with two
  labels can take either name). A plain line-by-line count, which also counts the netlists' simulator commands and
  library cells no schematic describes, gives about 61 %; the largest differences left are committed netlists from
  an older version of their schematic (one testbench on three shuttles).
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
  none of the failures' own findings. An oscillation found with undriven inputs is re-run at its worst condition
  with them held at 0 V, mid-supply and full supply: settled at every level, it is a note; still swinging, a
  warning naming the level. On 10 backtest rows (development set), 10 of 11 such oscillations became notes and chips that work with a
  design-risk finding fell from 9 of 21 to 6 of 21; the in-scope op-amp failure keeps its warning.
- The no-model baseline chooses among the cells it can test before taking the largest: on the 28 backtest rows,
  cells powered up go from 59 to 74; an op-amp chip whose layout netlist's standard cells had taken every slot goes
  from 0 tested cells to 6.
- The designer's own testbench loops, measured: every instance whose output returns to its own input in a
  testbench is cut there and its loop gain measured at 45 conditions. On the testbenches of the 28 backtest rows:
  the op-amp chip that failed on silicon from instability ("self oscillates a bit" in unity feedback) has phase
  margin 1–34° at 45 of 45 conditions in its follower testbenches (2 of its testbenches); no finding on a chip that
  works; the 3-stage op-amp whose phase margin was low on silicon (blamed on the pad path and board) measures
  60–67° with a Tiny Tapeout pad, so it is not caught.
  Across all 98 cloned repositories (counts only): 509 testbenches, 57 of them in 20 repositories close a loop around
  an instance (77 loops); 13 loops are judged as amplifiers in negative feedback (the rest are open-loop AC benches,
  switches or loops with no gain), and 5 are flagged, all one op-amp design used in two projects: the one that
  oscillated on silicon, and a twin-tee oscillator built from it.
- Silicon backtest, a **development set** (no-model baseline, v6, 3 Nov, every review exactly as the server runs
  it; counts only, as `tools/score_backtest.py` prints them). The rule changes of 1-2 Nov were each prompted by a
  chip in this same set (the 555 timer's loop, an analog switch's floating pins, a top cell's unwired pins), so the
  improvement from v2 to v5 is partly fitted to these chips and says less about chips Kaaval has not seen; each
  change was also checked for side effects on the 98 cloned repositories where that could be counted. Result: of 52 Tiny Tapeout analog chips with silicon feedback, 28 cloned rows
  reviewed in 3.1 h. Of the 7 that failed in a way Kaaval checks, 3 are flagged by the rule of their failure:
  the op-amp with stability trouble (phase margin 1-34° in its own follower testbench), the bandgap with a second
  operating point (two states), the relaxation oscillator with a low analog output (weak output under the pad
  load). Missed: a supply-domain error, a board-load workaround, a 3-stage op-amp's phase margin (60-67° even with
  a pad), and a design whose layout has sub-cells missing from its repository. Chips that work with at least one
  design-risk finding: 6 of 21 (v5: 7 of 21; v3: 9 of 21; v2: 11 of 16), each one to be read before it is called a false
  alarm. Split by whether a chip prompted a change: on the 18 rows whose review led to no rule or code
  change (no clean held-out set exists yet: TT09's chip pages carry no silicon feedback), 2 of 4 in-scope failures
  are flagged by their rule and 1 of 14 working chips has a design-risk finding. Scope labels are the Kaaval author's reading of each outcome, not the designers'; with 7 in scope, one
  chip moves a rate by 14 points, so no percentage is given.
- Muse arm vs rules arm, measured 4 Nov. **Held-out seeded bugs (10 designs, 6 planted start-up bugs):** designer's testbenches alone 0/6; brute-force rules 4/6 with 3 false alarms; Muse Spark 3/6 with **0 false alarms**. Muse does not find more of these bugs than brute force; it finds them without crying wolf. **Pin roles (189 ports):** rules 143/189 (76 %), Muse Spark 173/189 (92 %), every supply, ground, enable and reset right (80/80). The answer key was drafted by an AI from circuit evidence and has not been checked by an engineer yet.

- In a project's own CI: `tools/kaaval_check.py` runs the same review on a checkout (findings, JSON, SARIF, exit
  code 1 on a design-risk warning) and `action.yml` makes it a GitHub Action whose findings show on the pull
  request's files. On backtest row 8: 3 warnings, each SARIF result on its schematic, exit 1. (The Action itself
  waits for CI minutes to run.)

## Built during the event (startup-track label)

All of `SruSanAI/kaaval`, starting 27 Oct: the netlister, the engine, the planner, the review UI, chip view,
Silicon Twin, the timing outputs (`.lib`, SDC, supply corner), layout against schematic and post-layout re-runs,
the backtest tools.

Pre-existing and declared: Minnal, our private analog designer. Kaaval runs standalone without it. With
`MINNAL_URL`/`MINNAL_KEY` set, only the sizing-fix search is called on Minnal.

## Where Muse Spark is load-bearing

- Reading a repo's docs, schematics and schematic images into blocks, risks and pin roles (preflight with the real
  key, 4 Nov: it counts a bandgap's 8 transistors from its schematic image, matching our netlist, and names the
  block "1:29 PNP PTAT generator, leakage-only startup"). Without a model, stability is measured only where the
  designer's own testbench closes a loop; anywhere else the cut needs the topology understood, which is Muse's plan.
- Choosing the power-up sequences and chip-context tests per block (all 5 of its plans on a 23-cell design valid,
  including 2 stability cuts it placed), with high reasoning effort.
- Answering the designer's questions from the review's own findings, citing them (live: a ring-oscillator review
  answered in 16 s, every number taken from the review).

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
- [x] FILL lines above filled or dropped
- [ ] kaaval-public flipped to public (Sanjay)
- [ ] Live product URL (docs/HOSTING.md)
- [ ] Video recorded (real runs, 1×) and uploaded
- [ ] Form submitted before 5 Nov 6:30 AM IST

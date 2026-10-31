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
- **FILL** silicon backtest: counts only, as `tools/score_backtest.py` prints them (rows, findings, unconfirmed, rails).
- **FILL** Muse arm vs rules arm (held-out ablation; pin roles, where the rules arm scores 143/189 = 76 %).

## Built during the event (startup-track label)

All of `SruSanAI/kaaval`, starting 27 Oct: the netlister, the engine, the planner, the review UI, chip view,
Silicon Twin, the timing outputs (`.lib`, SDC, supply corner), the backtest tools.

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
| 0:20–0:50 | Paste a Tiny Tapeout repo. Muse Spark's plan streams in: blocks, pin roles with evidence, tests chosen. |
| 0:50–1:30 | Proving: the 45-condition grid fills. A finding opens: failing device on its sheet, waveform on click. |
| 1:30–2:00 | Sequence matrix: rail order × condition. Click the 3.3 V-leads-by-1-ms cell: stays off. |
| 2:00–2:30 | Chip view, down to the transistor. Into the timing flow: SDC clock, supply corner, `.lib` refused at ±1 mV. |
| 2:30–2:50 | Fix proposed, re-simulated at 45 conditions. Download the ngspice deck a designer can run without Kaaval. |
| 2:50–3:00 | Repo link, "pre-silicon simulation on open PDKs, not foundry sign-off". |

## Checklist

- [ ] Muse preflight passes (docs/MUSE_READY.md, step 1)
- [ ] FILL lines above filled or dropped
- [ ] kaaval-public flipped to public (Sanjay)
- [ ] Live product URL (docs/HOSTING.md)
- [ ] Video recorded (real runs, 1×) and uploaded
- [ ] Form submitted before 5 Nov 6:30 AM IST

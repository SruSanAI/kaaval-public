# Kaaval demo tile

A Tiny Tapeout-shaped analog project **of our own**, made for Kaaval's demos (written by `tools/make_demo_tapeout.py`).
Two blocks, each with a flaw on purpose (review it: upload a zip of this folder):
- `xschem/kv_ref.sch`, a self-biased (beta-multiplier) current reference **without a start-up device**: DC analysis
  finds its working bias, but powered up from 0 V it can stay at zero current (0 uA at 30 of 45 conditions in
  Kaaval's README). Testbench `xschem/tb_ref.sch` (1.8 V, a 50 kOhm load, operating point).
- `xschem/kv_amp.sch`, a two-stage Miller op-amp with a **0.5 pF compensation capacitor, too small for its 10 pF load**.
  Testbench `xschem/tb_amp.sch` wires it as a unity follower: Kaaval finds that loop and measures its thin phase margin.

Never submitted to a shuttle.

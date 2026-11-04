# Kaaval demo tile

A Tiny Tapeout-shaped analog project **of our own**, made for Kaaval's demos (written by `tools/make_demo_tapeout.py`):
three analog blocks, schematics drawn with wires (`xschem/`), two of them also drawn as sky130 layouts with Magic
(`mag/`, and the whole tile in `mag/tt_um_kaaval_demo.mag`). Every block has flaws **on purpose**; review it by
uploading a zip of this folder.

| Block | Planted flaw | What a review should find |
|---|---|---|
| `kv_ref`, a self-biased (beta-multiplier) current reference | no start-up device | powered up from 0 V it stays at zero current at most conditions (DC analysis still finds the working bias) |
| `kv_amp`, a two-stage Miller op-amp | 0.5 pF compensation for a 10 pF load | `tb_amp.sch` wires it as a unity follower: that loop's phase margin is thin |
| `kv_amp` layout | M8 drawn 12 um wide, 16 um in the schematic | layout against schematic: the sizes differ |
| `kv_bias`, a resistor-set current mirror | sized SI-style, `W=2u L=1u` | sky130 reads W and L in micrometres, so these are 2e-6 um wide: a units trap |

The layouts draw only the transistors: the schematics' resistors, capacitor and current source are ideal parts with no
PDK model. Testbenches: `tb_ref.sch`, `tb_amp.sch`, `tb_bias.sch` (1.8 V, operating point). Never submitted to a shuttle.

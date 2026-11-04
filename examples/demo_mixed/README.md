# Kaaval demo tile 2: two rails

A second Tiny Tapeout-shaped analog project **of our own** (written by `tools/make_demo_mixed.py`), with both the 1.8 V
(VDPWR) and the 3.3 V (VAPWR) rail. Every block has a flaw **on purpose**; review it by uploading a zip of this folder.

| Block | What it is | Planted flaw |
|---|---|---|
| `xschem/kv_osc.sch` | a five-stage current-starved ring oscillator (`tb_osc.sch`: 1.8 V, 20 fF, 4 us transient) | its starving bias is a 200k / 100k divider, 0.6 V: near threshold |
| `spice/kv_xref.spice` | a 1.8 V beta-multiplier current reference | its only start-up is a 200 fF kick from the 3.3 V rail |
| `spice/kv_cross.spice` | a 3.3 V inverter driving a 1.8 V inverter | no level shifter: 1.8 V thin-oxide gates see the 3.3 V swing |
| `spice/kv_vref.spice` | a 0.9 V reference to its pad | a 100k / 100k divider: 50 kOhm output resistance |

Never submitted to a shuttle.

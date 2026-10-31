# Kaaval demo tile

A Tiny Tapeout-shaped analog project **of our own**, made for Kaaval's demos (written by `tools/make_demo_tapeout.py`).
Its one block, `xschem/kv_ref.sch`, is a self-biased (beta-multiplier) current reference **without a start-up device, on
purpose**: DC analysis finds its working bias, but powered up from 0 V it can stay at zero current. Kaaval's README
reports this reference staying at 0 uA at 30 of 45 conditions. Review it: upload a zip of this folder.

`xschem/tb_ref.sch` is its testbench (1.8 V, a 50 kOhm load, operating point). Never submitted to a shuttle.

v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/vsource.sym} -300 0 0 0 {name=V1 value=1.8}
C {devices/lab_pin.sym} -300 -30 0 0 {name=p1 lab=vdd}
C {devices/gnd.sym} -300 30 0 0 {name=l2 lab=GND}
C {devices/vsource.sym} -200 0 0 0 {name=V2 value=0.9}
C {devices/lab_pin.sym} -200 -30 0 0 {name=p3 lab=inp}
C {devices/gnd.sym} -200 30 0 0 {name=l4 lab=GND}
C {kv_amp.sym} 100 0 0 0 {name=x2}
C {devices/lab_pin.sym} 100 -60 0 0 {name=p5 lab=vdd}
C {devices/gnd.sym} 100 60 0 0 {name=l6 lab=GND}
C {devices/lab_pin.sym} 20 20 0 0 {name=p7 lab=inp}
C {devices/lab_pin.sym} 20 -20 0 0 {name=p8 lab=out}
C {devices/lab_pin.sym} 180 0 0 1 {name=p9 lab=out}
C {devices/capa.sym} 300 60 0 0 {name=C2 value=10p}
C {devices/lab_pin.sym} 300 30 0 0 {name=p10 lab=out}
C {devices/gnd.sym} 300 90 0 0 {name=l11 lab=GND}
C {sky130_fd_pr/corner.sym} -300 -200 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} -300 200 0 0 {name=s1 only_toplevel=false value=".op
.save all"}

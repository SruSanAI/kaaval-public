v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/vsource.sym} -200 0 0 0 {name=V1 value=1.8}
C {devices/lab_pin.sym} -200 -30 0 0 {name=p1 lab=vdd}
C {devices/gnd.sym} -200 30 0 0 {name=l2 lab=GND}
C {kv_ref.sym} 100 0 0 0 {name=x1}
C {devices/lab_pin.sym} 100 -60 0 0 {name=p3 lab=vdd}
C {devices/gnd.sym} 100 60 0 0 {name=l4 lab=GND}
C {devices/lab_pin.sym} 180 0 0 1 {name=p5 lab=iout}
C {devices/res.sym} 300 60 0 0 {name=R2 value=50k}
C {devices/lab_pin.sym} 300 30 0 0 {name=p6 lab=iout}
C {devices/gnd.sym} 300 90 0 0 {name=l7 lab=GND}
C {sky130_fd_pr/corner.sym} -200 -200 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} -200 200 0 0 {name=s1 only_toplevel=false value=".op
.save all"}

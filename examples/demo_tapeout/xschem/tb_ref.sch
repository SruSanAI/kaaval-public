v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/vsource.sym} -200 0 0 0 {name=V1 value=1.8}
C {kv_ref.sym} 100 0 0 0 {name=x1}
C {devices/res.sym} 300 60 0 0 {name=R2 value=50k}
N -200 -30 -200 -120 {lab=vdd}
N -200 -120 100 -120 {lab=vdd}
N 100 -120 100 -60 {lab=vdd}
N 180 0 300 0 {lab=iout}
N 300 0 300 30 {lab=iout}
N -200 160 300 160 {lab=0}
N -200 30 -200 160 {lab=0}
N 100 60 100 160 {lab=0}
N 300 90 300 160 {lab=0}
C {devices/lab_pin.sym} -200 -120 0 0 {name=p1 lab=vdd}
C {devices/lab_pin.sym} 300 0 0 1 {name=p2 lab=iout}
C {devices/gnd.sym} -200 160 0 0 {name=l3 lab=GND}
C {sky130_fd_pr/corner.sym} -200 -300 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} -200 260 0 0 {name=s1 only_toplevel=false value=".op
.save all"}

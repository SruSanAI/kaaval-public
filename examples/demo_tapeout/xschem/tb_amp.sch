v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/vsource.sym} -300 0 0 0 {name=V1 value=1.8}
C {devices/vsource.sym} -160 80 0 0 {name=V2 value=0.9}
C {kv_amp.sym} 100 0 0 0 {name=x2}
C {devices/capa.sym} 300 60 0 0 {name=C2 value=10p}
N -300 -30 -300 -160 {lab=vdd}
N -300 -160 100 -160 {lab=vdd}
N 100 -160 100 -60 {lab=vdd}
N 180 0 220 0 {lab=out}
N 220 0 300 0 {lab=out}
N 300 0 300 30 {lab=out}
N 220 0 220 -120 {lab=out}
N 220 -120 -20 -120 {lab=out}
N -20 -120 -20 -20 {lab=out}
N -20 -20 20 -20 {lab=out}
N -160 50 -160 20 {lab=inp}
N -160 20 20 20 {lab=inp}
N -300 200 300 200 {lab=0}
N -300 30 -300 200 {lab=0}
N -160 110 -160 200 {lab=0}
N 100 60 100 200 {lab=0}
N 300 90 300 200 {lab=0}
C {devices/lab_pin.sym} -300 -160 0 0 {name=p1 lab=vdd}
C {devices/lab_pin.sym} 300 0 0 1 {name=p2 lab=out}
C {devices/lab_pin.sym} -160 20 0 0 {name=p3 lab=inp}
C {devices/gnd.sym} -300 200 0 0 {name=l4 lab=GND}
C {sky130_fd_pr/corner.sym} -300 -320 0 0 {name=CORNER only_toplevel=true corner=tt}
C {devices/code_shown.sym} -300 300 0 0 {name=s1 only_toplevel=false value=".op
.save all"}

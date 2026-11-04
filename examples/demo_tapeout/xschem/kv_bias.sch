v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/iopin.sym} -200 -100 0 0 {name=p1 lab=vdd}
C {devices/iopin.sym} -200 300 0 0 {name=p2 lab=vss}
C {devices/iopin.sym} 300 0 0 0 {name=p3 lab=ibias}
C {devices/res.sym} 0 0 0 0 {name=R1 value=10k}
C {sky130_fd_pr/nfet_01v8.sym} -20 150 0 0 {name=M1
W=2u
L=1u
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 0 150 0 1 {name=p4 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 180 150 0 0 {name=M2
W=2u
L=1u
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 200 150 0 1 {name=p5 lab=vss}
N -200 -100 0 -100 {lab=vdd}
N 0 -100 0 -30 {lab=vdd}
N 0 30 0 120 {lab=nb}
N -40 150 -60 150 {lab=nb}
N -60 150 -60 80 {lab=nb}
N -60 80 0 80 {lab=nb}
N 160 150 140 150 {lab=nb}
N 140 150 140 80 {lab=nb}
N 140 80 0 80 {lab=nb}
N 200 120 200 0 {lab=ibias}
N 200 0 300 0 {lab=ibias}
N -200 300 200 300 {lab=vss}
N 0 180 0 300 {lab=vss}
N 200 180 200 300 {lab=vss}
C {devices/lab_pin.sym} -60 80 0 0 {name=p6 lab=nb}

v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/iopin.sym} -300 -100 0 0 {name=p1 lab=vdd}
C {devices/iopin.sym} -300 400 0 0 {name=p2 lab=vss}
C {devices/iopin.sym} 560 100 0 0 {name=p3 lab=iout}
C {sky130_fd_pr/pfet_01v8.sym} 0 0 0 0 {name=M3
W=8
L=2
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 0 0 1 {name=p4 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 200 0 0 0 {name=M4
W=8
L=2
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 0 0 1 {name=p5 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 400 0 0 0 {name=M5
W=8
L=2
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 420 0 0 1 {name=p6 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 200 0 0 {name=M1
W=4
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 200 0 1 {name=p7 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 200 0 0 {name=M2
W=16
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 200 0 1 {name=p8 lab=vss}
C {devices/res.sym} 220 300 0 0 {name=R1 value=20k}
N -300 -100 420 -100 {lab=vdd}
N 20 -100 20 -30 {lab=vdd}
N 220 -100 220 -30 {lab=vdd}
N 420 -100 420 -30 {lab=vdd}
N -300 400 220 400 {lab=vss}
N 20 230 20 400 {lab=vss}
N 220 330 220 400 {lab=vss}
N 220 230 220 270 {lab=s2}
N 20 30 20 170 {lab=n1}
N -20 200 -40 200 {lab=n1}
N -40 200 -40 120 {lab=n1}
N -40 120 20 120 {lab=n1}
N 180 200 160 200 {lab=n1}
N 160 200 160 120 {lab=n1}
N 160 120 20 120 {lab=n1}
N 220 30 220 170 {lab=n2}
N 180 0 160 0 {lab=n2}
N 160 0 160 60 {lab=n2}
N 160 60 220 60 {lab=n2}
N -20 0 -40 0 {lab=n2}
N -40 0 -40 -60 {lab=n2}
N -40 -60 160 -60 {lab=n2}
N 160 -60 160 0 {lab=n2}
N 380 0 360 0 {lab=n2}
N 360 0 360 60 {lab=n2}
N 360 60 220 60 {lab=n2}
N 420 30 420 100 {lab=iout}
N 420 100 560 100 {lab=iout}
C {devices/lab_pin.sym} -40 120 0 0 {name=p9 lab=n1}
C {devices/lab_pin.sym} 360 60 0 1 {name=p10 lab=n2}
C {devices/lab_pin.sym} 220 250 0 1 {name=p11 lab=s2}

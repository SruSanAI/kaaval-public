v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/iopin.sym} -300 -100 0 0 {name=p1 lab=vdd}
C {devices/iopin.sym} -300 -60 0 0 {name=p2 lab=vss}
C {devices/iopin.sym} -300 -20 0 0 {name=p3 lab=iout}
C {sky130_fd_pr/nfet_01v8.sym} 0 200 0 0 {name=M1
W=4
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 170 0 1 {name=p4 lab=n1}
C {devices/lab_pin.sym} -20 200 0 0 {name=p5 lab=n1}
C {devices/lab_pin.sym} 20 230 0 1 {name=p6 lab=vss}
C {devices/lab_pin.sym} 20 200 0 1 {name=p7 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 200 0 0 {name=M2
W=16
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 170 0 1 {name=p8 lab=n2}
C {devices/lab_pin.sym} 180 200 0 0 {name=p9 lab=n1}
C {devices/lab_pin.sym} 220 230 0 1 {name=p10 lab=s2}
C {devices/lab_pin.sym} 220 200 0 1 {name=p11 lab=vss}
C {devices/res.sym} 220 320 0 0 {name=R1 value=20k}
C {devices/lab_pin.sym} 220 290 0 0 {name=p12 lab=s2}
C {devices/lab_pin.sym} 220 350 0 0 {name=p13 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} 0 0 0 0 {name=M3
W=8
L=2
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 30 0 1 {name=p14 lab=n1}
C {devices/lab_pin.sym} -20 0 0 0 {name=p15 lab=n2}
C {devices/lab_pin.sym} 20 -30 0 1 {name=p16 lab=vdd}
C {devices/lab_pin.sym} 20 0 0 1 {name=p17 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 200 0 0 0 {name=M4
W=8
L=2
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 30 0 1 {name=p18 lab=n2}
C {devices/lab_pin.sym} 180 0 0 0 {name=p19 lab=n2}
C {devices/lab_pin.sym} 220 -30 0 1 {name=p20 lab=vdd}
C {devices/lab_pin.sym} 220 0 0 1 {name=p21 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 400 0 0 0 {name=M5
W=8
L=2
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 420 30 0 1 {name=p22 lab=iout}
C {devices/lab_pin.sym} 380 0 0 0 {name=p23 lab=n2}
C {devices/lab_pin.sym} 420 -30 0 1 {name=p24 lab=vdd}
C {devices/lab_pin.sym} 420 0 0 1 {name=p25 lab=vdd}

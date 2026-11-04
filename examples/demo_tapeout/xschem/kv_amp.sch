v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/iopin.sym} -400 -160 0 0 {name=p1 lab=vdd}
C {devices/iopin.sym} -400 -120 0 0 {name=p2 lab=vss}
C {devices/iopin.sym} -400 -80 0 0 {name=p3 lab=inp}
C {devices/iopin.sym} -400 -40 0 0 {name=p4 lab=inn}
C {devices/iopin.sym} -400 0 0 0 {name=p5 lab=out}
C {devices/isource.sym} -200 100 0 0 {name=I1 value=20u}
C {devices/lab_pin.sym} -200 70 0 0 {name=p6 lab=vdd}
C {devices/lab_pin.sym} -200 130 0 0 {name=p7 lab=vb}
C {sky130_fd_pr/nfet_01v8.sym} -100 300 0 0 {name=M6
W=4
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} -80 270 0 1 {name=p8 lab=vb}
C {devices/lab_pin.sym} -120 300 0 0 {name=p9 lab=vb}
C {devices/lab_pin.sym} -80 330 0 1 {name=p10 lab=vss}
C {devices/lab_pin.sym} -80 300 0 1 {name=p11 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 100 400 0 0 {name=M5
W=8
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 120 370 0 1 {name=p12 lab=tail}
C {devices/lab_pin.sym} 80 400 0 0 {name=p13 lab=vb}
C {devices/lab_pin.sym} 120 430 0 1 {name=p14 lab=vss}
C {devices/lab_pin.sym} 120 400 0 1 {name=p15 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 0 250 0 0 {name=M1
W=8
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 220 0 1 {name=p16 lab=o1}
C {devices/lab_pin.sym} -20 250 0 0 {name=p17 lab=inn}
C {devices/lab_pin.sym} 20 280 0 1 {name=p18 lab=tail}
C {devices/lab_pin.sym} 20 250 0 1 {name=p19 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 250 0 0 {name=M2
W=8
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 220 0 1 {name=p20 lab=o2a}
C {devices/lab_pin.sym} 180 250 0 0 {name=p21 lab=inp}
C {devices/lab_pin.sym} 220 280 0 1 {name=p22 lab=tail}
C {devices/lab_pin.sym} 220 250 0 1 {name=p23 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} 0 0 0 0 {name=M3
W=8
L=1
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 30 0 1 {name=p24 lab=o1}
C {devices/lab_pin.sym} -20 0 0 0 {name=p25 lab=o1}
C {devices/lab_pin.sym} 20 -30 0 1 {name=p26 lab=vdd}
C {devices/lab_pin.sym} 20 0 0 1 {name=p27 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 200 0 0 0 {name=M4
W=8
L=1
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 30 0 1 {name=p28 lab=o2a}
C {devices/lab_pin.sym} 180 0 0 0 {name=p29 lab=o1}
C {devices/lab_pin.sym} 220 -30 0 1 {name=p30 lab=vdd}
C {devices/lab_pin.sym} 220 0 0 1 {name=p31 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 400 0 0 0 {name=M7
W=32
L=0.5
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 420 30 0 1 {name=p32 lab=out}
C {devices/lab_pin.sym} 380 0 0 0 {name=p33 lab=o2a}
C {devices/lab_pin.sym} 420 -30 0 1 {name=p34 lab=vdd}
C {devices/lab_pin.sym} 420 0 0 1 {name=p35 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 400 300 0 0 {name=M8
W=16
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 420 270 0 1 {name=p36 lab=out}
C {devices/lab_pin.sym} 380 300 0 0 {name=p37 lab=vb}
C {devices/lab_pin.sym} 420 330 0 1 {name=p38 lab=vss}
C {devices/lab_pin.sym} 420 300 0 1 {name=p39 lab=vss}
C {devices/capa.sym} 300 150 0 0 {name=C1 value=0.5p}
C {devices/lab_pin.sym} 300 120 0 0 {name=p40 lab=o2a}
C {devices/lab_pin.sym} 300 180 0 0 {name=p41 lab=ncz}
C {devices/res.sym} 500 150 0 0 {name=R1 value=2k}
C {devices/lab_pin.sym} 500 120 0 0 {name=p42 lab=ncz}
C {devices/lab_pin.sym} 500 180 0 0 {name=p43 lab=out}

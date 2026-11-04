v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/iopin.sym} -300 -120 0 0 {name=p1 lab=vdd}
C {devices/iopin.sym} -300 520 0 0 {name=p2 lab=vss}
C {devices/iopin.sym} -300 170 0 0 {name=p3 lab=inp}
C {devices/iopin.sym} -300 230 0 0 {name=p4 lab=inn}
C {devices/iopin.sym} 620 290 0 0 {name=p5 lab=out}
C {sky130_fd_pr/pfet_01v8.sym} 0 0 0 0 {name=M3
W=8
L=1
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 0 0 1 {name=p6 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 200 0 0 0 {name=M4
W=8
L=1
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 0 0 1 {name=p7 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 460 0 0 0 {name=M7
W=32
L=0.5
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 480 0 0 1 {name=p8 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 230 0 0 {name=M1
W=8
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 230 0 1 {name=p9 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 230 0 0 {name=M2
W=8
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 230 0 1 {name=p10 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 120 380 0 0 {name=M5
W=8
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 140 380 0 1 {name=p11 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} -160 380 0 0 {name=M6
W=4
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} -140 380 0 1 {name=p12 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 460 380 0 0 {name=M8
W=16
L=1
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 480 380 0 1 {name=p13 lab=vss}
C {devices/isource.sym} -140 60 0 0 {name=I1 value=20u}
C {devices/capa.sym} 360 120 0 0 {name=C1 value=0.5p}
C {devices/res.sym} 360 230 0 0 {name=R1 value=2k}
N -300 -120 480 -120 {lab=vdd}
N 20 -120 20 -30 {lab=vdd}
N 220 -120 220 -30 {lab=vdd}
N 480 -120 480 -30 {lab=vdd}
N -140 -120 -140 30 {lab=vdd}
N -300 520 480 520 {lab=vss}
N -140 410 -140 520 {lab=vss}
N 140 410 140 520 {lab=vss}
N 480 410 480 520 {lab=vss}
N 20 30 20 200 {lab=o1}
N -20 0 -40 0 {lab=o1}
N -40 0 -40 100 {lab=o1}
N -40 100 20 100 {lab=o1}
N 180 0 160 0 {lab=o1}
N 160 0 160 100 {lab=o1}
N 160 100 20 100 {lab=o1}
N 220 30 220 200 {lab=o2a}
N 440 0 400 0 {lab=o2a}
N 400 0 400 60 {lab=o2a}
N 400 60 220 60 {lab=o2a}
N 360 90 360 60 {lab=o2a}
N 360 150 360 200 {lab=ncz}
N 480 30 480 350 {lab=out}
N 360 260 360 290 {lab=out}
N 360 290 480 290 {lab=out}
N 480 290 620 290 {lab=out}
N 20 260 20 300 {lab=tail}
N 20 300 220 300 {lab=tail}
N 220 260 220 300 {lab=tail}
N 140 300 140 350 {lab=tail}
N -140 90 -140 350 {lab=vb}
N -180 380 -200 380 {lab=vb}
N -200 380 -200 330 {lab=vb}
N -200 330 -140 330 {lab=vb}
N -200 380 -200 460 {lab=vb}
N -200 460 420 460 {lab=vb}
N 100 380 80 380 {lab=vb}
N 80 380 80 460 {lab=vb}
N 440 380 420 380 {lab=vb}
N 420 380 420 460 {lab=vb}
N -20 230 -300 230 {lab=inn}
N 180 230 160 230 {lab=inp}
N 160 230 160 170 {lab=inp}
N 160 170 -300 170 {lab=inp}
C {devices/lab_pin.sym} -40 100 0 0 {name=p14 lab=o1}
C {devices/lab_pin.sym} 400 0 0 0 {name=p15 lab=o2a}
C {devices/lab_pin.sym} 20 300 0 0 {name=p16 lab=tail}
C {devices/lab_pin.sym} -200 460 0 0 {name=p17 lab=vb}
C {devices/lab_pin.sym} 360 175 0 1 {name=p18 lab=ncz}

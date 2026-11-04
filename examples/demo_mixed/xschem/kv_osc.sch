v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/iopin.sym} -320 -80 0 0 {name=p1 lab=vdd}
C {devices/iopin.sym} -320 380 0 0 {name=p2 lab=vss}
C {devices/iopin.sym} 960 75 0 0 {name=p3 lab=osc}
N -320 -80 840 -80 {lab=vdd}
N -320 380 840 380 {lab=vss}
C {devices/res.sym} -260 60 0 0 {name=R1 value=200k}
C {devices/res.sym} -260 300 0 0 {name=R2 value=100k}
N -260 -80 -260 30 {lab=vdd}
N -260 90 -260 270 {lab=vbn}
N -260 330 -260 380 {lab=vss}
N -260 200 780 200 {lab=vbn}
C {sky130_fd_pr/pfet_01v8.sym} 0 0 0 0 {name=MP1
W=2
L=0.5
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 0 0 1 {name=p4 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 150 0 0 {name=MN1
W=1
L=0.5
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 150 0 1 {name=p5 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 0 300 0 0 {name=MS1
W=1
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 20 300 0 1 {name=p6 lab=vss}
N 20 -80 20 -30 {lab=vdd}
N -20 0 -20 150 {lab=s0}
N 20 30 20 120 {lab=s1}
N 20 180 20 270 {lab=t1}
N 20 330 20 380 {lab=vss}
N -20 200 -20 300 {lab=vbn}
N 20 75 180 75 {lab=s1}
C {sky130_fd_pr/pfet_01v8.sym} 200 0 0 0 {name=MP2
W=2
L=0.5
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 0 0 1 {name=p7 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 200 150 0 0 {name=MN2
W=1
L=0.5
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 150 0 1 {name=p8 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 300 0 0 {name=MS2
W=1
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 220 300 0 1 {name=p9 lab=vss}
N 220 -80 220 -30 {lab=vdd}
N 180 0 180 150 {lab=s1}
N 220 30 220 120 {lab=s2}
N 220 180 220 270 {lab=t2}
N 220 330 220 380 {lab=vss}
N 180 200 180 300 {lab=vbn}
N 220 75 380 75 {lab=s2}
C {sky130_fd_pr/pfet_01v8.sym} 400 0 0 0 {name=MP3
W=2
L=0.5
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 420 0 0 1 {name=p10 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 400 150 0 0 {name=MN3
W=1
L=0.5
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 420 150 0 1 {name=p11 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 400 300 0 0 {name=MS3
W=1
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 420 300 0 1 {name=p12 lab=vss}
N 420 -80 420 -30 {lab=vdd}
N 380 0 380 150 {lab=s2}
N 420 30 420 120 {lab=s3}
N 420 180 420 270 {lab=t3}
N 420 330 420 380 {lab=vss}
N 380 200 380 300 {lab=vbn}
N 420 75 580 75 {lab=s3}
C {sky130_fd_pr/pfet_01v8.sym} 600 0 0 0 {name=MP4
W=2
L=0.5
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 620 0 0 1 {name=p13 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 600 150 0 0 {name=MN4
W=1
L=0.5
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 620 150 0 1 {name=p14 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 600 300 0 0 {name=MS4
W=1
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 620 300 0 1 {name=p15 lab=vss}
N 620 -80 620 -30 {lab=vdd}
N 580 0 580 150 {lab=s3}
N 620 30 620 120 {lab=s4}
N 620 180 620 270 {lab=t4}
N 620 330 620 380 {lab=vss}
N 580 200 580 300 {lab=vbn}
N 620 75 780 75 {lab=s4}
C {sky130_fd_pr/pfet_01v8.sym} 800 0 0 0 {name=MP5
W=2
L=0.5
nf=1
mult=1
model=pfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 820 0 0 1 {name=p16 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 800 150 0 0 {name=MN5
W=1
L=0.5
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 820 150 0 1 {name=p17 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 800 300 0 0 {name=MS5
W=1
L=2
nf=1
mult=1
model=nfet_01v8
spiceprefix=X
}
C {devices/lab_pin.sym} 820 300 0 1 {name=p18 lab=vss}
N 820 -80 820 -30 {lab=vdd}
N 780 0 780 150 {lab=s4}
N 820 30 820 120 {lab=s5}
N 820 180 820 270 {lab=t5}
N 820 330 820 380 {lab=vss}
N 780 200 780 300 {lab=vbn}
N 820 75 860 75 {lab=osc}
N 860 75 960 75 {lab=osc}
N 860 75 860 440 {lab=osc}
N 860 440 -60 440 {lab=osc}
N -60 440 -60 75 {lab=osc}
N -60 75 -20 75 {lab=osc}
C {devices/lab_pin.sym} -260 150 0 0 {name=p19 lab=vbn}

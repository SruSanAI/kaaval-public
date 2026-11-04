`default_nettype none
// Kaaval mixed-domain demo tile: four analog blocks, two rails (1.8 V VDPWR, 3.3 V VAPWR).
module tt_um_kaaval_mixed (
    input  wire       VGND,
    input  wire       VDPWR,
    input  wire       VAPWR,
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    inout  wire [7:0] ua,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  assign uo_out = 8'b0;
  assign uio_out = 8'b0;
  assign uio_oe = 8'b0;
  kv_osc   o0 (.vdd(VDPWR), .vss(VGND), .osc(ua[0]));
  kv_xref  x0 (.vdd(VDPWR), .avdd(VAPWR), .vss(VGND), .iout(ua[1]));
  kv_cross c0 (.vdd(VDPWR), .avdd(VAPWR), .vss(VGND), .in(ua[2]), .out(ua[3]));
  kv_vref  v0 (.vdd(VDPWR), .vss(VGND), .vref(ua[4]));
endmodule

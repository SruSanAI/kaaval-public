`default_nettype none
// Kaaval demo tile: one analog block, the current reference (xschem/kv_ref.sch), output on ua[0].
module tt_um_kaaval_demo (
    input  wire       VGND,
    input  wire       VDPWR,
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
  kv_ref r0 (.vdd(VDPWR), .vss(VGND), .iout(ua[0]));
endmodule

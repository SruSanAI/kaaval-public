// Kaaval test fixture (our own logic): a reset synchroniser and counter that release an analog block's enable
// 50 clock cycles (1 MHz) after the chip's reset is released. Simulated with: iverilog en_release.v && vvp a.out
`timescale 1ns/1ps
module en_release(input clk, input rst_n, output reg en);
  reg [1:0] sync; reg [5:0] n;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) begin sync <= 0; n <= 0; en <= 0; end
    else begin
      sync <= {sync[0], 1'b1};
      if (sync[1] && n != 50) n <= n + 1;
      en <= sync[1] && n == 50;
    end
endmodule

module tb;
  reg clk = 0, rst_n = 0; wire en;
  en_release dut(.clk(clk), .rst_n(rst_n), .en(en));
  always #500 clk = ~clk;
  initial begin $dumpfile("en_release.vcd"); $dumpvars(0, tb); #2000 rst_n = 1; #80000 $finish; end
endmodule

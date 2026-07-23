module dv_formal(input logic clk);
  logic [2:0] counter = 3'd0;

  always_ff @(posedge clk)
    counter <= counter + 3'd1;

  always_comb
    assert (counter < 4'd8);
endmodule

module dv_qualification;
  logic [3:0] left = 4'd3;
  logic [3:0] right = 4'd5;

  initial begin
    #1;
    if ((left + right) != 4'd8)
      $fatal(1, "qualification arithmetic failed");
    $display("dv-platform qualification passed");
    $finish;
  end
endmodule

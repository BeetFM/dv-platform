module sky130_openram_fixture (
    input  wire        clk,
    input  wire        write_enable,
    input  wire [7:0]  address,
    input  wire [31:0] write_data,
    output reg  [31:0] read_data
);
  reg [31:0] memory [0:255];
  always @(posedge clk) begin
    if (write_enable)
      memory[address] <= write_data;
    read_data <= memory[address];
  end
endmodule

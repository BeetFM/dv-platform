module native_reset_register (
    input wire clk,
    input wire rst_n,
    input wire [7:0] data_i,
    output reg [7:0] data_o
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_o <= 8'h00;
        end else begin
            data_o <= data_i;
        end
    end
endmodule

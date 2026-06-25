module simple_counter #(
    parameter int WIDTH = 8
) (
    input logic clk,
    input logic rst_n,
    input logic enable_i,
    output logic [WIDTH-1:0] count_o
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count_o <= '0;
        end else if (enable_i) begin
            count_o <= count_o + 1'b1;
        end
    end
endmodule

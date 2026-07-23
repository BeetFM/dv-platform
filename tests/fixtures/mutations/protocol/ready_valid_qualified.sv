module ready_valid_qualified #(
    parameter int MUTANT = 0
) (
    input logic clk,
    input logic rst,
    input logic in_valid,
    output logic in_ready,
    input logic [7:0] in_data,
    output logic out_valid,
    input logic out_ready,
    output logic [7:0] out_data
);
    logic full;
    logic [7:0] stored;

    assign in_ready = MUTANT == 1 ? 1'b0 : !full;
    assign out_valid = MUTANT == 2 && full && !out_ready ? 1'b0 : full;
    assign out_data = MUTANT == 3 && full && !out_ready ? stored + 1'b1
                    : MUTANT == 4 ? stored ^ 8'h01 : stored;

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            full <= 1'b0;
            stored <= '0;
        end else begin
            if (in_valid && in_ready) begin
                full <= 1'b1;
                stored <= in_data;
            end
            if (out_valid && out_ready)
                full <= 1'b0;
        end
    end
endmodule

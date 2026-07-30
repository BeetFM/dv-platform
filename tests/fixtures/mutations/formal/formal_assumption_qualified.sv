module formal_assumption_qualified #(
    parameter integer MUTANT = 0
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [3:0] range_i,
    input  logic       stable_i,
    input  logic       trigger,
    output logic       response,
    output logic       invariant
);
    logic tracker;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            response <= 1'b0;
            tracker <= 1'b0;
        end else begin
            response <= trigger;
            tracker <= ~tracker;
        end
    end

    assign invariant = (MUTANT == 1) ? 1'b0 : 1'b1;
endmodule

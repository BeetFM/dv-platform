module formal_contract_qualified #(
    parameter integer MUTANT = 0
) (
    input  logic clk,
    input  logic rst_n,
    input  logic trigger,
    output logic response,
    output logic invariant_ok
);
    logic trigger_d1;
    logic trigger_d2;
    logic trigger_d3;

    always_comb begin
        invariant_ok = rst_n && (MUTANT != 3);
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            trigger_d1 <= 1'b0;
            trigger_d2 <= 1'b0;
            trigger_d3 <= 1'b0;
            response <= 1'b0;
        end else begin
            trigger_d1 <= trigger;
            trigger_d2 <= trigger_d1;
            trigger_d3 <= trigger_d2;
            if (MUTANT == 1)
                response <= 1'b0;
            else if (MUTANT == 2)
                response <= trigger_d3;
            else if (MUTANT == 4)
                response <= 1'b1;
            else
                response <= trigger_d1;
        end
    end
endmodule

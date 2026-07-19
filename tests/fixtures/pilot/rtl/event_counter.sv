module event_counter #(
    parameter int WIDTH = 8
) (
    input  logic             phase,
    input  logic             clear_n,
    input  logic             request,
    output logic [WIDTH-1:0] result
);
    always_ff @(posedge phase or posedge clear_n) begin
        if (clear_n) begin
            result <= '0;
        end else if (request) begin
            result <= result + 1'b1;
        end
    end
endmodule

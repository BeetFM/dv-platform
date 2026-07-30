module ready_valid_qualified (
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

    assign in_ready = !full;
    assign out_valid = full;
    assign out_data = stored;

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

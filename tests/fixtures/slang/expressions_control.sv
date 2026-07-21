module expressions_control #(
    parameter int WIDTH = 8
) (
    input  logic                   clk,
    input  logic                   rst_n,
    input  logic                   enable,
    input  logic signed [WIDTH-1:0] a,
    input  logic        [WIDTH-1:0] b,
    input  logic        [1:0]      mode,
    output logic signed [WIDTH:0]  result,
    output logic        [WIDTH-1:0] sync_result
);
    logic signed [WIDTH:0] next_result;

    always_comb begin
        casez (mode)
            2'b00: next_result = $signed(a) + $signed({1'b0, b});
            2'b01: next_result = enable ? $signed(a) - $signed(b) : '0;
            2'b1?: next_result = $signed(a[WIDTH-1:0]);
            default: next_result = '0;
        endcase
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            result <= '0;
        else if (enable)
            result <= next_result;
    end


    always_ff @(posedge clk) begin
        if (!rst_n)
            sync_result <= '0;
        else if (enable)
            sync_result <= a;
    end
endmodule

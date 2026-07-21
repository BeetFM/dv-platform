module generated_child #(
    parameter int WIDTH = 8
) (
    input  logic [WIDTH-1:0] value_i,
    output logic [WIDTH-1:0] value_o
);
    assign value_o = value_i;
endmodule

module hierarchy_generate_memory #(
    parameter int WIDTH = 8,
    parameter int COUNT = 2,
    parameter bit ENABLE_EXTRA = 1'b1
) (
    input  logic             clk,
    input  logic             write_en,
    input  logic [1:0]       address,
    input  logic [WIDTH-1:0] write_data,
    output logic [WIDTH-1:0] read_data
);
    logic [WIDTH-1:0] memory [0:3];
    logic [WIDTH-1:0] chain [0:COUNT];
    assign chain[0] = write_data;

    for (genvar index = 0; index < COUNT; index++) begin : g_chain
        generated_child #(.WIDTH(WIDTH)) u_child (
            .value_i(chain[index]),
            .value_o(chain[index + 1])
        );
    end

    if (ENABLE_EXTRA) begin : g_extra
        logic [WIDTH-1:0] extra;
        assign extra = chain[COUNT];
    end

    always_ff @(posedge clk) begin
        if (write_en)
            memory[address] <= write_data;
        read_data <= memory[address];
    end
endmodule

module stream_buffer #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 2,
    localparam int PTR_WIDTH = (DEPTH <= 2) ? 1 : $clog2(DEPTH)
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             in_valid,
    output logic             in_ready,
    input  logic [WIDTH-1:0] in_data,
    output logic             out_valid,
    input  logic             out_ready,
    output logic [WIDTH-1:0] out_data
);
    logic [WIDTH-1:0] storage [0:DEPTH-1];
    logic [PTR_WIDTH-1:0] read_ptr;
    logic [PTR_WIDTH-1:0] write_ptr;
    logic [PTR_WIDTH:0] occupancy;
    logic push;
    logic pop;

    assign out_valid = occupancy != '0;
    assign in_ready = (occupancy < (PTR_WIDTH + 1)'(DEPTH)) && !(out_valid && !out_ready);
    assign out_data = out_valid ? storage[read_ptr] : '0;
    assign push = in_valid && in_ready;
    assign pop = out_valid && out_ready;

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            read_ptr <= '0;
            write_ptr <= '0;
            occupancy <= '0;
        end else begin
            if (push) begin
                storage[write_ptr] <= in_data;
                write_ptr <= (write_ptr == PTR_WIDTH'(DEPTH - 1)) ? '0 : write_ptr + 1'b1;
            end
            if (pop) begin
                read_ptr <= (read_ptr == PTR_WIDTH'(DEPTH - 1)) ? '0 : read_ptr + 1'b1;
            end
            case ({push, pop})
                2'b10: occupancy <= occupancy + 1'b1;
                2'b01: occupancy <= occupancy - 1'b1;
                default: occupancy <= occupancy;
            endcase
        end
    end
endmodule

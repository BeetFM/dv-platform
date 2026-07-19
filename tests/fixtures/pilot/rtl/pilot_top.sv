module pilot_top #(
    parameter int WIDTH = 8
) (
    input  logic             system_clk,
    input  logic             system_reset,
    input  logic             request,
    output logic [WIDTH-1:0] result,
    input  logic             in_valid,
    output logic             in_ready,
    input  logic [WIDTH-1:0] in_data,
    output logic             out_valid,
    input  logic             out_ready,
    output logic [WIDTH-1:0] out_data
);
    event_counter #(.WIDTH(WIDTH)) u_counter (
        .phase   (system_clk),
        .clear_n (system_reset),
        .request (request),
        .result  (result)
    );

    stream_buffer #(.WIDTH(WIDTH), .DEPTH(2)) u_stream (
        .clk       (system_clk),
        .rst       (system_reset),
        .in_valid  (in_valid),
        .in_ready  (in_ready),
        .in_data   (in_data),
        .out_valid (out_valid),
        .out_ready (out_ready),
        .out_data  (out_data)
    );
endmodule

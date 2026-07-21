package types_pkg;
    parameter int BASE_WIDTH = 4;
    typedef enum logic [1:0] {IDLE, BUSY, DONE} state_t;
    typedef struct packed {
        state_t state;
        logic signed [BASE_WIDTH-1:0] data;
    } payload_t;
    typedef struct packed {
        payload_t payload;
        logic parity;
    } packet_t;
endpackage

interface stream_if #(parameter int WIDTH = 8);
    logic valid;
    logic ready;
    logic [WIDTH-1:0] data;
    modport source(output valid, output data, input ready);
    modport sink(input valid, input data, output ready);
endinterface

module types_interfaces (
    input logic clk,
    stream_if.source tx [0:1],
    stream_if.sink rx [0:1]
);
    import types_pkg::*;
    types_pkg::packet_t packets [0:1];
    assign tx[0].valid = rx[0].valid;
    assign tx[0].data = {{(8-BASE_WIDTH){1'b0}}, packets[0].payload.data};
    assign rx[0].ready = tx[0].ready;
endmodule

module types_interfaces_top(input logic clk);
    stream_if tx [0:1]();
    stream_if rx [0:1]();
    types_interfaces u_dut(.clk, .tx, .rx);
endmodule

module apb4_slave (
    input logic        pclk,
    input logic        presetn,
    input logic [31:0] paddr,
    input logic        psel,
    input logic        penable,
    input logic        pwrite,
    input logic [31:0] pwdata,
    input logic [3:0]  pstrb,
    output logic [31:0] prdata,
    output logic        pready,
    output logic        pslverr
);
endmodule

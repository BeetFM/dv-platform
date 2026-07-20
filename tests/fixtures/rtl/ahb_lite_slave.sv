module ahb_lite_slave (
    input  logic        hclk,
    input  logic        hresetn,
    input  logic [31:0] haddr,
    input  logic [1:0]  htrans,
    input  logic        hwrite,
    input  logic        hsel,
    input  logic        hready,
    input  logic [31:0] hwdata,
    output logic [31:0] hrdata,
    output logic        hreadyout,
    output logic        hresp
);
endmodule

module apb4_slave (
    input  logic        pclk,
    input  logic        presetn,
    input  logic [31:0] paddr,
    input  logic        psel,
    input  logic        penable,
    input  logic        pwrite,
    input  logic [31:0] pwdata,
    input  logic [3:0]  pstrb,
    output logic [31:0] prdata,
    output logic        pready,
    output logic        pslverr
);
    logic [31:0] control;

    always_ff @(posedge pclk or negedge presetn) begin
        if (!presetn) begin
            control <= '0;
        end else if (psel && penable && pready && pwrite && paddr == 32'h0) begin
            for (int byte_index = 0; byte_index < 4; byte_index++) begin
                if (pstrb[byte_index])
                    control[byte_index * 8 +: 8] <= pwdata[byte_index * 8 +: 8];
            end
        end
    end

    always_comb begin
        pready = psel && penable;
        pslverr = psel && penable && paddr != 32'h0;
        prdata = paddr == 32'h0 ? control : '0;
    end
endmodule

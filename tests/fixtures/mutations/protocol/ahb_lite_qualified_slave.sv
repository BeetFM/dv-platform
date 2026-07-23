module ahb_lite_qualified_slave #(
    parameter int MUTANT = 0
) (
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
    logic [7:0] rw_value;
    logic [7:0] ro_value;
    logic [7:0] w1c_value;
    logic       waiting;

    always_ff @(posedge hclk or negedge hresetn) begin
        if (!hresetn) begin
            rw_value  <= MUTANT == 6 ? 8'h00 : 8'h12;
            ro_value  <= 8'h34;
            w1c_value <= 8'hff;
            waiting   <= 1'b0;
            hreadyout <= 1'b0;
        end else begin
            hreadyout <= 1'b1;
            if (hsel && htrans[1] && hready) begin
                if (MUTANT == 5) begin
                    hreadyout <= 1'b0;
                end else if (!waiting) begin
                    waiting   <= 1'b1;
                    hreadyout <= 1'b0;
                end else begin
                    waiting   <= 1'b0;
                    hreadyout <= 1'b1;
                    if (hwrite && haddr == 32'h0 && MUTANT != 1) begin
                        rw_value <= hwdata[7:0];
                        if (MUTANT == 2)
                            ro_value <= hwdata[15:8];
                        if (MUTANT == 3)
                            w1c_value <= hwdata[23:16];
                        else
                            w1c_value <= w1c_value & ~hwdata[23:16];
                    end
                end
            end else begin
                waiting <= 1'b0;
            end
        end
    end

    always_comb begin
        hrdata = haddr == 32'h0 ? {8'h00, w1c_value, ro_value, rw_value} : '0;
        hresp = hsel && htrans[1] && hreadyout && haddr != 32'h0;
        if (MUTANT == 4)
            hresp = 1'b0;
    end
endmodule

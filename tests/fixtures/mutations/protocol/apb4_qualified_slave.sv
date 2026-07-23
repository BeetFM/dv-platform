module apb4_qualified_slave #(
    parameter int MUTANT = 0
) (
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
    logic [7:0] rw_value;
    logic [7:0] ro_value;
    logic [7:0] w1c_value;
    logic [1:0] wait_count;

    always_ff @(posedge pclk or negedge presetn) begin
        if (!presetn) begin
            rw_value   <= MUTANT == 9 ? 8'h00 : 8'h12;
            ro_value   <= 8'h34;
            w1c_value  <= 8'hff;
            wait_count <= '0;
            pready     <= 1'b0;
        end else begin
            pready <= 1'b0;
            if (MUTANT == 6) begin
                // A completion pulse in setup is ignored by a compliant master,
                // then disappears for the access phase.
                pready <= psel && !penable;
            end else if (psel && penable) begin
                if (MUTANT == 7) begin
                    pready <= 1'b0;
                end else if (wait_count == 2) begin
                    pready     <= 1'b1;
                    wait_count <= '0;
                    if (pwrite && paddr == 32'h0 && MUTANT != 1) begin
                        if ((MUTANT == 2) || pstrb[0])
                            rw_value <= pwdata[7:0];
                        if (MUTANT == 3 && ((MUTANT == 2) || pstrb[1]))
                            ro_value <= pwdata[15:8];
                        if ((MUTANT == 2) || pstrb[2]) begin
                            if (MUTANT == 4)
                                w1c_value <= pwdata[23:16];
                            else
                                w1c_value <= w1c_value & ~pwdata[23:16];
                        end
                    end
                end else begin
                    wait_count <= wait_count + 1'b1;
                end
            end else begin
                wait_count <= '0;
            end
        end
    end

    always_comb begin
        if (paddr == 32'h0)
            prdata = {8'h00, w1c_value, ro_value, rw_value};
        else
            prdata = '0;
        if (MUTANT == 8 && psel && penable && !pready)
            prdata = prdata ^ {30'b0, wait_count};
        if (MUTANT == 5)
            pslverr = 1'b0;
        else
            pslverr = psel && penable && pready && paddr != 32'h0;
    end
endmodule

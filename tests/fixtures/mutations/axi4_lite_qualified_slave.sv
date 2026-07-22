module axi4_lite_qualified_slave #(
    parameter int MUTANT = 0
) (
    input logic aclk, input logic aresetn,
    input logic [3:0] awaddr, input logic awvalid, output logic awready,
    input logic [7:0] wdata, input logic [0:0] wstrb, input logic wvalid, output logic wready,
    output logic [1:0] bresp, output logic bvalid, input logic bready,
    input logic [3:0] araddr, input logic arvalid, output logic arready,
    output logic [7:0] rdata, output logic [1:0] rresp, output logic rvalid, input logic rready
);
    logic [7:0] control;
    logic [3:0] held_awaddr;
    logic [7:0] held_wdata;
    logic [0:0] held_wstrb;
    logic have_aw, have_w;

    assign awready = !bvalid && (MUTANT == 8 ? 1'b1 : !have_aw) && (MUTANT == 1 ? wvalid : 1'b1);
    assign wready = !bvalid && !have_w && (MUTANT == 1 ? awvalid : 1'b1);
    assign arready = MUTANT == 10 ? 1'b1 : !rvalid;

    always_ff @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            control <= 8'h78;
            held_awaddr <= '0; held_wdata <= '0; held_wstrb <= '0;
            have_aw <= 1'b0; have_w <= 1'b0;
            bvalid <= 1'b0; bresp <= 2'b00;
            rvalid <= 1'b0; rdata <= '0; rresp <= 2'b00;
        end else begin
            if (awvalid && awready) begin held_awaddr <= awaddr; have_aw <= 1'b1; end
            if (wvalid && wready) begin held_wdata <= wdata; held_wstrb <= wstrb; have_w <= 1'b1; end
            if (MUTANT == 9 && !bvalid && ((have_aw && !have_w) || (have_w && !have_aw))) begin
                bvalid <= 1'b1;
                bresp <= 2'b00;
            end
            if (have_aw && have_w && !bvalid) begin
                if (MUTANT != 2) bvalid <= 1'b1;
                bresp <= (held_awaddr == 0 || MUTANT == 7) ? 2'b00 : 2'b10;
                if (held_awaddr == 0) begin
                    for (int lane = 0; lane < 1; lane++)
                        if (held_wstrb[lane] || MUTANT == 6)
                            control[lane * 8 +: 8] <= held_wdata[lane * 8 +: 8];
                end
                have_aw <= 1'b0; have_w <= 1'b0;
            end else if (bvalid && bready) begin
                bvalid <= 1'b0;
            end else if (MUTANT == 3 && bvalid && !bready) begin
                bresp <= bresp + 1'b1;
            end
            if (arvalid && arready) begin
                rvalid <= 1'b1;
                rdata <= araddr == 0 ? control : '0;
                rresp <= (araddr == 0 || MUTANT == 7) ? 2'b00 : 2'b10;
            end else if (rvalid && rready) begin
                rvalid <= 1'b0;
            end else if (MUTANT == 4 && rvalid && !rready) begin
                rvalid <= 1'b0;
            end else if (MUTANT == 5 && rvalid && !rready) begin
                rdata <= rdata + 1'b1;
                rresp <= rresp + 1'b1;
            end
        end
    end
endmodule

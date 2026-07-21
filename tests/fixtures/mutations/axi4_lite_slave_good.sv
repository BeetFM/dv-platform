module axi4_lite_slave (
    input  logic        aclk,
    input  logic        aresetn,
    input  logic [31:0] awaddr,
    input  logic        awvalid,
    output logic        awready,
    input  logic [31:0] wdata,
    input  logic [3:0]  wstrb,
    input  logic        wvalid,
    output logic        wready,
    output logic [1:0]  bresp,
    output logic        bvalid,
    input  logic        bready,
    input  logic [31:0] araddr,
    input  logic        arvalid,
    output logic        arready,
    output logic [31:0] rdata,
    output logic [1:0]  rresp,
    output logic        rvalid,
    input  logic        rready
);
    logic [31:0] control;
    logic [31:0] held_awaddr;
    logic [31:0] held_wdata;
    logic [3:0]  held_wstrb;
    logic        have_aw;
    logic        have_w;

    assign awready = !have_aw && !bvalid;
    assign wready  = !have_w && !bvalid;
    assign arready = !rvalid;

    always_ff @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            control <= '0;
            held_awaddr <= '0;
            held_wdata <= '0;
            held_wstrb <= '0;
            have_aw <= 1'b0;
            have_w <= 1'b0;
            bvalid <= 1'b0;
            bresp <= 2'b00;
            rvalid <= 1'b0;
            rresp <= 2'b00;
            rdata <= '0;
        end else begin
            if (awready && awvalid) begin
                held_awaddr <= awaddr;
                have_aw <= 1'b1;
            end
            if (wready && wvalid) begin
                held_wdata <= wdata;
                held_wstrb <= wstrb;
                have_w <= 1'b1;
            end
            if (have_aw && have_w && !bvalid) begin
                bvalid <= 1'b1;
                bresp <= held_awaddr == 32'h0 ? 2'b00 : 2'b10;
                if (held_awaddr == 32'h0) begin
                    for (int byte_index = 0; byte_index < 4; byte_index++) begin
                        if (held_wstrb[byte_index])
                            control[byte_index * 8 +: 8] <= held_wdata[byte_index * 8 +: 8];
                    end
                end
                have_aw <= 1'b0;
                have_w <= 1'b0;
            end else if (bvalid && bready) begin
                bvalid <= 1'b0;
            end
            if (arready && arvalid) begin
                rvalid <= 1'b1;
                rresp <= araddr == 32'h0 ? 2'b00 : 2'b10;
                rdata <= araddr == 32'h0 ? control : '0;
            end else if (rvalid && rready) begin
                rvalid <= 1'b0;
            end
        end
    end
endmodule

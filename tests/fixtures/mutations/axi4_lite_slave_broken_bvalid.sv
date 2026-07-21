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
    logic accepted_aw;
    logic accepted_w;

    assign awready = !accepted_aw;
    assign wready = !accepted_w;
    assign arready = !rvalid;

    always_ff @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            accepted_aw <= 1'b0;
            accepted_w <= 1'b0;
            bvalid <= 1'b0;
            bresp <= 2'b00;
            rvalid <= 1'b0;
            rresp <= 2'b00;
            rdata <= '0;
        end else begin
            if (awready && awvalid)
                accepted_aw <= 1'b1;
            if (wready && wvalid)
                accepted_w <= 1'b1;
            // Deliberate mutation: BVALID is only a pulse and drops under backpressure.
            bvalid <= accepted_aw && accepted_w;
            if (bvalid) begin
                accepted_aw <= 1'b0;
                accepted_w <= 1'b0;
            end
            if (arready && arvalid) begin
                rvalid <= 1'b1;
                rdata <= '0;
                rresp <= 2'b00;
            end else if (rvalid && rready) begin
                rvalid <= 1'b0;
            end
        end
    end
endmodule

module broad_protocol_endpoints #(
    parameter int MUTANT = 0
) (
    input logic clk,
    input logic reset_n,

    input logic [3:0] x_awid, input logic [31:0] x_awaddr, input logic [7:0] x_awlen,
    input logic [2:0] x_awsize, input logic [1:0] x_awburst, input logic x_awvalid,
    output logic x_awready, input logic [31:0] x_wdata, input logic [3:0] x_wstrb,
    input logic x_wlast, input logic x_wvalid, output logic x_wready,
    output logic [3:0] x_bid, output logic [1:0] x_bresp, output logic x_bvalid, input logic x_bready,
    input logic [3:0] x_arid, input logic [31:0] x_araddr, input logic [7:0] x_arlen,
    input logic [2:0] x_arsize, input logic [1:0] x_arburst, input logic x_arvalid,
    output logic x_arready, output logic [3:0] x_rid, output logic [31:0] x_rdata,
    output logic [1:0] x_rresp, output logic x_rlast, output logic x_rvalid, input logic x_rready,

    input logic wb_cyc, input logic wb_stb, input logic wb_we, input logic [31:0] wb_adr,
    input logic [31:0] wb_dat_w, input logic [3:0] wb_sel, output logic wb_ack,
    output logic wb_stall, output logic wb_err, output logic wb_rty, output logic [31:0] wb_dat_r,
    input logic [2:0] wb_cti, input logic [1:0] wb_bte,

    input logic mm_read, input logic mm_write, input logic [31:0] mm_address,
    input logic [31:0] mm_writedata, input logic [3:0] mm_byteenable,
    input logic [7:0] mm_burstcount, output logic mm_waitrequest,
    output logic [31:0] mm_readdata, output logic mm_readdatavalid,
    output logic mm_writeresponsevalid, output logic [1:0] mm_response,

    input logic ast_valid, output logic ast_ready, input logic [31:0] ast_data,
    input logic ast_startofpacket, input logic ast_endofpacket, input logic [1:0] ast_empty,
    input logic [3:0] ast_channel, input logic [1:0] ast_error,

    input logic h_hsel, input logic [31:0] h_haddr, input logic [1:0] h_htrans,
    input logic h_hwrite, input logic [2:0] h_hsize, input logic [2:0] h_hburst,
    input logic [31:0] h_hwdata, output logic [31:0] h_hrdata,
    output logic h_hready, output logic h_hresp,

    input logic tl_a_valid, output logic tl_a_ready, input logic [2:0] tl_a_opcode,
    input logic [2:0] tl_a_param, input logic [3:0] tl_a_size, input logic [3:0] tl_a_source,
    input logic [31:0] tl_a_address, input logic [3:0] tl_a_mask, input logic [31:0] tl_a_data,
    output logic tl_d_valid, input logic tl_d_ready, output logic [2:0] tl_d_opcode,
    output logic [1:0] tl_d_param, output logic [3:0] tl_d_size, output logic [3:0] tl_d_source,
    output logic tl_d_denied, output logic [31:0] tl_d_data, output logic tl_d_corrupt
);
    logic x_have_aw, x_have_w;

    assign x_awready = MUTANT == 1 ? 1'b0 : !x_have_aw && !x_bvalid;
    assign x_wready = !x_have_w && !x_bvalid;
    assign x_arready = !x_rvalid;
    assign wb_stall = 1'b0;
    assign wb_ack = MUTANT == 3 ? 1'b0 : wb_cyc && wb_stb;
    assign wb_err = 1'b0;
    assign wb_rty = 1'b0;
    assign wb_dat_r = wb_adr ^ 32'h55aa_aa55;
    assign mm_waitrequest = 1'b0;
    assign ast_ready = MUTANT == 5 ? 1'b0 : 1'b1;
    assign h_hready = MUTANT == 6 ? 1'b0 : 1'b1;
    assign h_hresp = 1'b0;
    assign h_hrdata = h_haddr ^ 32'ha5a5_5a5a;
    assign tl_a_ready = !tl_d_valid;

    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            x_have_aw <= 1'b0; x_have_w <= 1'b0; x_bvalid <= 1'b0;
            x_bid <= '0; x_bresp <= '0; x_rvalid <= 1'b0; x_rid <= '0;
            x_rdata <= '0; x_rresp <= '0; x_rlast <= 1'b0;
            mm_readdata <= '0; mm_readdatavalid <= 1'b0;
            mm_writeresponsevalid <= 1'b0; mm_response <= '0;
            tl_d_valid <= 1'b0; tl_d_opcode <= '0; tl_d_param <= '0;
            tl_d_size <= '0; tl_d_source <= '0; tl_d_denied <= 1'b0;
            tl_d_data <= '0; tl_d_corrupt <= 1'b0;
        end else begin
            if (x_awvalid && x_awready) begin x_have_aw <= 1'b1; x_bid <= x_awid; end
            if (x_wvalid && x_wready) x_have_w <= 1'b1;
            if (x_have_aw && x_have_w) begin x_bvalid <= MUTANT == 2 ? 1'b0 : 1'b1; x_have_aw <= 1'b0; x_have_w <= 1'b0; end
            if (x_bvalid && x_bready) x_bvalid <= 1'b0;
            if (x_arvalid && x_arready) begin
                x_rvalid <= 1'b1; x_rid <= x_arid; x_rdata <= x_araddr;
                x_rresp <= 2'b00; x_rlast <= 1'b1;
            end
            if (x_rvalid && x_rready) x_rvalid <= 1'b0;

            mm_readdatavalid <= MUTANT == 4 ? 1'b0 : mm_read;
            mm_writeresponsevalid <= mm_write;
            if (mm_read) mm_readdata <= mm_address ^ 32'hcafe_f00d;

            if (tl_a_valid && tl_a_ready) begin
                tl_d_valid <= MUTANT == 7 ? 1'b0 : 1'b1; tl_d_opcode <= 3'b001; tl_d_size <= tl_a_size;
                tl_d_source <= tl_a_source; tl_d_data <= tl_a_data;
            end
            if (tl_d_valid && tl_d_ready) tl_d_valid <= 1'b0;
        end
    end
endmodule

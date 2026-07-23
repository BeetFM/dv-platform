module axi4_stream_profile_source #(
    parameter integer MUTANT = 0
) (
    input  logic        clk,
    input  logic        reset_n,
    output logic        tvalid,
    input  logic        tready,
    output logic [31:0] tdata,
    output logic [3:0]  tkeep,
    output logic [3:0]  tstrb,
    output logic        tlast,
    output logic [3:0]  tid,
    output logic [3:0]  tdest,
    output logic [3:0]  tuser
);
    always_ff @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            tvalid <= 1'b0;
            tdata  <= 32'h1234_5678;
            tkeep  <= 4'hf;
            tstrb  <= 4'hf;
            tlast  <= 1'b1;
            tid    <= 4'h3;
            tdest  <= 4'h5;
            tuser  <= 4'h7;
        end else begin
            tvalid <= 1'b1;
            if (MUTANT == 1)
                tkeep <= 4'h0;
            if (MUTANT == 2)
                tlast <= 1'b0;
            if (MUTANT == 3 && !tready)
                tdata <= tdata + 1'b1;
            if (MUTANT == 4 && !tready)
                tid <= tid + 1'b1;
        end
    end
endmodule

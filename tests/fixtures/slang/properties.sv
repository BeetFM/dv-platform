module properties (
    input logic clk,
    input logic rst_n,
    input logic req,
    input logic ack
);
    ap_ack: assert property (@(posedge clk) disable iff (!rst_n) req |=> ack);
    cp_req: cover property (@(posedge clk) disable iff (!rst_n) req ##1 ack);

    always_comb begin
        ai_known: assert (!$isunknown(req));
        ci_req: cover (req);
    end
endmodule

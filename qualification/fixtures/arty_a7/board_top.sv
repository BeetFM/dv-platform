module board_top (
    input  logic       CLK100MHZ,
    input  logic [3:0] sw,
    input  logic [3:0] btn,
    input  logic [7:0] ja,
    input  logic       uart_rxd_out,
    output logic [3:0] led,
    output logic       uart_txd_in
);
    logic [25:0] counter = '0;

    always_ff @(posedge CLK100MHZ) begin
        counter <= counter + 1'b1;
        led <= sw ^ btn ^ counter[25:22];
        uart_txd_in <= uart_rxd_out ^ ^ja;
    end
endmodule

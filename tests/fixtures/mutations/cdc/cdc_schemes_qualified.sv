module cdc_schemes_qualified #(
    parameter int MUTANT = 0
) (
    input  logic src_clk,
    input  logic dst_clk,
    input  logic rst_n,
    input  logic async_toggle,
    input  logic async_pulse,
    input  logic req_async,
    input  logic ack_async,
    input  logic [15:0] payload,
    input  logic [3:0] gray_async,
    input  logic branch0,
    input  logic branch1,
    output logic toggle_meta,
    output logic toggle_sync,
    output logic pulse_meta,
    output logic pulse_sync,
    output logic req_meta,
    output logic req_sync,
    output logic ack_meta,
    output logic ack_sync,
    output logic [15:0] payload_observed,
    output logic [3:0] gray_meta,
    output logic [3:0] gray_sync,
    output logic branch0_meta,
    output logic branch0_sync,
    output logic branch1_meta,
    output logic branch1_sync,
    output logic coherent
);
    always_ff @(posedge dst_clk or negedge rst_n) begin
        if (!rst_n) begin
            toggle_meta <= 1'b0;
            toggle_sync <= 1'b0;
            pulse_meta <= 1'b0;
            pulse_sync <= 1'b0;
            req_meta <= 1'b0;
            req_sync <= 1'b0;
            gray_meta <= '0;
            gray_sync <= '0;
            branch0_meta <= 1'b0;
            branch0_sync <= 1'b0;
            branch1_meta <= 1'b0;
            branch1_sync <= 1'b0;
        end else begin
            toggle_meta <= async_toggle;
            toggle_sync <= MUTANT == 1 ? ~toggle_meta : toggle_meta;
            pulse_meta <= async_pulse;
            pulse_sync <= MUTANT == 2 ? ~pulse_meta : pulse_meta;
            req_meta <= req_async;
            req_sync <= MUTANT == 3 ? ~req_meta : req_meta;
            gray_meta <= gray_async;
            gray_sync <= MUTANT == 5 ? {gray_meta[2:0], gray_meta[3]} : gray_meta;
            branch0_meta <= branch0;
            branch0_sync <= branch0_meta;
            branch1_meta <= branch1;
            branch1_sync <= branch1_meta;
        end
    end

    assign coherent = MUTANT == 7 ? (branch0_sync ^ branch1_sync) : (branch0_sync & branch1_sync);

    always_ff @(posedge src_clk or negedge rst_n) begin
        if (!rst_n) begin
            ack_meta <= 1'b0;
            ack_sync <= 1'b0;
        end else begin
            ack_meta <= ack_async;
            ack_sync <= MUTANT == 4 ? ~ack_meta : ack_meta;
        end
    end

    // Payload is governed by the handshake stability assumption. Keeping this
    // reference makes the intent visible in normalized structural evidence.
    always_ff @(posedge dst_clk or negedge rst_n) begin
        if (!rst_n)
            payload_observed <= '0;
        else if (req_sync)
            payload_observed <= MUTANT == 6 ? ~payload : payload;
    end
endmodule

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
    input  logic payload,
    output logic toggle_meta,
    output logic toggle_sync,
    output logic pulse_meta,
    output logic pulse_sync,
    output logic req_meta,
    output logic req_sync,
    output logic ack_meta,
    output logic ack_sync
);
    always_ff @(posedge dst_clk or negedge rst_n) begin
        if (!rst_n) begin
            toggle_meta <= 1'b0;
            toggle_sync <= 1'b0;
            pulse_meta <= 1'b0;
            pulse_sync <= 1'b0;
            req_meta <= 1'b0;
            req_sync <= 1'b0;
        end else begin
            toggle_meta <= async_toggle;
            toggle_sync <= MUTANT == 1 ? ~toggle_meta : toggle_meta;
            pulse_meta <= async_pulse;
            pulse_sync <= MUTANT == 2 ? ~pulse_meta : pulse_meta;
            req_meta <= req_async;
            req_sync <= MUTANT == 3 ? ~req_meta : req_meta;
        end
    end

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
    logic payload_observed;
    always_ff @(posedge dst_clk or negedge rst_n) begin
        if (!rst_n)
            payload_observed <= 1'b0;
        else if (req_sync)
            payload_observed <= payload;
    end
endmodule

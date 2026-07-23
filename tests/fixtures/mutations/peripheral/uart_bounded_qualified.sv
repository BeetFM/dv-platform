module uart_bounded_qualified #(
    parameter integer MUTANT = 0,
    parameter integer CLOCKS_PER_BIT = 4
) (
    input  logic       clock,
    input  logic       reset,
    input  logic       tx_start,
    input  logic [7:0] tx_data,
    output logic       tx,
    output logic       tx_busy,
    input  logic       rx,
    output logic [7:0] rx_data,
    output logic       rx_valid,
    input  logic [1:0] parity_mode,
    input  logic       stop_bits,
    output logic       parity_error,
    output logic       framing_error,
    output logic       break_detect,
    output logic       overflow,
    input  logic       rx_clear
);
    localparam integer BAUD_LIMIT = MUTANT == 1 ? CLOCKS_PER_BIT - 1 : CLOCKS_PER_BIT;
    logic [7:0] tx_latched;
    logic [1:0] tx_parity_mode;
    logic tx_stop_bits;
    logic [3:0] tx_bit_index;
    integer tx_baud_count;
    logic tx_parity;

    logic receiving;
    logic [7:0] rx_shift;
    logic [3:0] rx_bit_index;
    integer rx_baud_count;
    integer break_count;
    logic rx_parity;

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) begin
            tx <= 1'b1;
            tx_busy <= 1'b0;
            tx_latched <= '0;
            tx_parity_mode <= '0;
            tx_stop_bits <= 1'b0;
            tx_bit_index <= '0;
            tx_baud_count <= 0;
            tx_parity <= 1'b0;
        end else if (!tx_busy) begin
            tx <= MUTANT == 5 ? 1'b0 : 1'b1;
            if (tx_start) begin
                tx_busy <= 1'b1;
                tx <= 1'b0;
                tx_latched <= tx_data;
                tx_parity_mode <= parity_mode;
                tx_stop_bits <= stop_bits;
                tx_parity <= MUTANT == 3 ? ~^tx_data : (parity_mode == 2 ? ~^tx_data : ^tx_data);
                tx_bit_index <= 0;
                tx_baud_count <= 0;
            end
        end else if (tx_baud_count == BAUD_LIMIT - 1) begin
            tx_baud_count <= 0;
            tx_bit_index <= tx_bit_index + 1'b1;
            if (tx_bit_index < 8)
                tx <= MUTANT == 2 ? tx_latched[3'd7-tx_bit_index[2:0]] : tx_latched[tx_bit_index[2:0]];
            else if (tx_bit_index == 8 && tx_parity_mode != 0)
                tx <= tx_parity;
            else if (
                (tx_parity_mode == 0 && tx_bit_index == 8) ||
                (tx_parity_mode != 0 && tx_bit_index == 9)
            )
                tx <= 1'b1;
            else if (
                tx_stop_bits && MUTANT != 4 &&
                ((tx_parity_mode == 0 && tx_bit_index == 9) ||
                 (tx_parity_mode != 0 && tx_bit_index == 10))
            )
                tx <= 1'b1;
            else begin
                tx <= MUTANT == 5 ? 1'b0 : 1'b1;
                tx_busy <= 1'b0;
            end
        end else begin
            tx_baud_count <= tx_baud_count + 1;
        end
    end

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) begin
            receiving <= 1'b0;
            rx_shift <= '0;
            rx_data <= '0;
            rx_valid <= 1'b0;
            rx_bit_index <= '0;
            rx_baud_count <= 0;
            parity_error <= 1'b0;
            framing_error <= 1'b0;
            overflow <= 1'b0;
            break_detect <= 1'b0;
            break_count <= 0;
            rx_parity <= 1'b0;
        end else begin
            if (rx_clear) begin
                rx_valid <= 1'b0;
                parity_error <= 1'b0;
                framing_error <= 1'b0;
                overflow <= 1'b0;
                break_detect <= 1'b0;
            end
            if (!rx) begin
                if (break_count < CLOCKS_PER_BIT * 16)
                    break_count <= break_count + 1;
                if (break_count >= CLOCKS_PER_BIT * 11 - 1 && MUTANT != 9)
                    break_detect <= 1'b1;
            end else begin
                break_count <= 0;
            end

            if (!receiving && !rx) begin
                receiving <= 1'b1;
                rx_bit_index <= 0;
                rx_baud_count <= 0;
                rx_shift <= 0;
                rx_parity <= 0;
            end else if (receiving && rx_baud_count == CLOCKS_PER_BIT - 1) begin
                rx_baud_count <= 0;
                if (rx_bit_index < 8) begin
                    if (MUTANT == 6)
                        rx_shift[3'd7-rx_bit_index[2:0]] <= rx;
                    else
                        rx_shift[rx_bit_index[2:0]] <= rx;
                    rx_parity <= rx_parity ^ rx;
                    rx_bit_index <= rx_bit_index + 1'b1;
                end else if (rx_bit_index == 8 && parity_mode != 0) begin
                    if (MUTANT != 7)
                        parity_error <= rx != (parity_mode == 2 ? ~rx_parity : rx_parity);
                    rx_bit_index <= rx_bit_index + 1'b1;
                end else begin
                    if (!rx && MUTANT != 8)
                        framing_error <= 1'b1;
                    if (stop_bits && (
                        (parity_mode == 0 && rx_bit_index == 8) ||
                        (parity_mode != 0 && rx_bit_index == 9)
                    )) begin
                        rx_bit_index <= rx_bit_index + 1'b1;
                    end else begin
                        receiving <= 1'b0;
                        rx_data <= rx_shift;
                        if (rx_valid && MUTANT != 10)
                            overflow <= 1'b1;
                        rx_valid <= 1'b1;
                    end
                end
            end else if (receiving) begin
                rx_baud_count <= rx_baud_count + 1;
            end
        end
    end
endmodule

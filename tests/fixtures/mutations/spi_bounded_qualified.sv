module spi_bounded_qualified #(
    parameter integer MUTANT = 0,
    parameter integer CLOCK_DIVIDER = 2
) (
    input  logic       clock,
    input  logic       reset,
    input  logic       start,
    input  logic [7:0] tx_data,
    output logic [7:0] rx_data,
    output logic       busy,
    output logic       done,
    output logic       sclk,
    output logic       mosi,
    input  logic       miso,
    output logic       cs_n,
    input  logic [1:0] mode,
    input  logic       lsb_first
);
    logic [7:0] tx_latched;
    logic [7:0] rx_shift;
    logic [1:0] mode_latched;
    logic lsb_latched;
    logic [3:0] sample_count;
    integer divider_count;
    logic last_sampled;
    logic idle_level;
    logic leading_edge;
    logic sample_edge;
    logic shift_edge;
    logic [2:0] selected_index;

    always_comb begin
        idle_level = MUTANT == 1 ? ~mode_latched[1] : mode_latched[1];
        leading_edge = sclk == idle_level;
        sample_edge = MUTANT == 2 ?
            (mode_latched[0] ? leading_edge : !leading_edge) :
            (mode_latched[0] ? !leading_edge : leading_edge);
        shift_edge = !sample_edge;
        selected_index = (lsb_latched && MUTANT != 5) ? sample_count[2:0] : 3'd7 - sample_count[2:0];
    end

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) begin
            rx_data <= '0;
            busy <= 1'b0;
            done <= 1'b0;
            sclk <= 1'b0;
            mosi <= 1'b0;
            cs_n <= 1'b1;
            tx_latched <= '0;
            rx_shift <= '0;
            mode_latched <= '0;
            lsb_latched <= 1'b0;
            sample_count <= 0;
            divider_count <= 0;
            last_sampled <= 1'b0;
        end else begin
            done <= 1'b0;
            if (!busy) begin
                cs_n <= 1'b1;
                sclk <= MUTANT == 1 ? ~mode[1] : mode[1];
                if (start) begin
                    busy <= 1'b1;
                    cs_n <= MUTANT == 3 ? 1'b1 : 1'b0;
                    mode_latched <= mode;
                    lsb_latched <= lsb_first;
                    tx_latched <= tx_data;
                    rx_shift <= 0;
                    sample_count <= 0;
                    divider_count <= 0;
                    last_sampled <= 1'b0;
                    mosi <= (lsb_first && MUTANT != 5) ? tx_data[0] : tx_data[7];
                    if (MUTANT == 9)
                        done <= 1'b1;
                end
            end else if (divider_count == (MUTANT == 8 ? CLOCK_DIVIDER - 2 : CLOCK_DIVIDER - 1)) begin
                divider_count <= 0;
                sclk <= ~sclk;
                if (sample_edge) begin
                    if (MUTANT == 6)
                        rx_shift[3'd7-selected_index] <= miso;
                    else
                        rx_shift[selected_index] <= miso;
                    if (sample_count == 7) begin
                        last_sampled <= 1'b1;
                        if (mode_latched[0] || MUTANT == 7) begin
                            rx_data <= MUTANT == 6 ? {miso, rx_shift[6:0]} :
                                (rx_shift | ({7'b0, miso} << selected_index));
                            busy <= 1'b0;
                            done <= 1'b1;
                            cs_n <= 1'b1;
                            sclk <= idle_level;
                        end
                    end else begin
                        sample_count <= sample_count + 1'b1;
                    end
                end else if (shift_edge) begin
                    if (last_sampled) begin
                        rx_data <= rx_shift;
                        busy <= 1'b0;
                        done <= 1'b1;
                        cs_n <= 1'b1;
                        sclk <= idle_level;
                    end else begin
                        mosi <= MUTANT == 4 ? tx_latched[3'd7-selected_index] : tx_latched[selected_index];
                    end
                end
            end else begin
                divider_count <= divider_count + 1;
            end
        end
    end
endmodule

module i2c_bounded_qualified #(
    parameter integer MUTANT = 0,
    parameter integer CLOCK_DIVIDER = 2
) (
    input  logic       clock,
    input  logic       reset,
    input  logic       start,
    input  logic       read,
    input  logic       repeated_start,
    input  logic [6:0] address,
    input  logic [7:0] write_data,
    output logic [7:0] read_data,
    output logic       read_valid,
    output logic       busy,
    output logic       done,
    output logic       ack_error,
    output logic       arbitration_lost,
    output logic       sda_drive_low,
    input  logic       sda_in,
    output logic       scl_drive_low,
    input  logic       scl_in
);
    localparam [3:0] IDLE = 0, START_HOLD = 1, BIT_LOW = 2, BIT_HIGH = 3,
                     ACK_LOW = 4, ACK_HIGH = 5, REP_LOW = 6, REP_HIGH = 7,
                     REP_START = 8, READ_LOW = 9, READ_HIGH = 10,
                     READ_NACK = 11, STOP_LOW = 12, STOP_HIGH = 13, STOP_RELEASE = 14;
    logic [3:0] state;
    logic [7:0] shift_byte;
    logic [7:0] read_shift;
    logic [2:0] bit_index;
    logic [1:0] byte_phase;
    logic repeated_latched;
    logic read_latched;
    logic [6:0] address_latched;
    logic [7:0] write_latched;
    integer phase_count;

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) begin
            state <= IDLE;
            shift_byte <= 0;
            read_shift <= 0;
            read_data <= 0;
            read_valid <= 0;
            busy <= 0;
            done <= 0;
            ack_error <= 0;
            arbitration_lost <= 0;
            sda_drive_low <= 0;
            scl_drive_low <= 0;
            bit_index <= 0;
            byte_phase <= 0;
            repeated_latched <= 0;
            read_latched <= 0;
            address_latched <= 0;
            write_latched <= 0;
            phase_count <= 0;
        end else begin
            done <= 0;
            case (state)
                IDLE: begin
                    busy <= 0;
                    arbitration_lost <= 0;
                    sda_drive_low <= 0;
                    scl_drive_low <= 0;
                    if (start && sda_in && scl_in) begin
                        busy <= 1;
                        ack_error <= 0;
                        arbitration_lost <= 0;
                        read_valid <= 0;
                        repeated_latched <= repeated_start;
                        read_latched <= read;
                        address_latched <= address;
                        write_latched <= write_data;
                        shift_byte <= {address, repeated_start ? 1'b0 : read};
                        byte_phase <= 0;
                        bit_index <= 0;
                        phase_count <= 0;
                        if (MUTANT == 1)
                            state <= BIT_LOW;
                        else begin
                            sda_drive_low <= 1;
                            state <= START_HOLD;
                        end
                    end
                end
                START_HOLD: begin
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        state <= BIT_LOW;
                    end else phase_count <= phase_count + 1;
                end
                BIT_LOW: begin
                    scl_drive_low <= 1;
                    sda_drive_low <= ~shift_byte[7-bit_index];
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        state <= BIT_HIGH;
                        scl_drive_low <= 0;
                    end else phase_count <= phase_count + 1;
                end
                BIT_HIGH: begin
                    scl_drive_low <= 0;
                    if (!scl_drive_low && scl_in == 0 && MUTANT != 5) begin
                        phase_count <= phase_count;
                    end else if (!sda_drive_low && !sda_in && scl_in && MUTANT != 6) begin
                        arbitration_lost <= 1;
                        busy <= 0;
                        done <= 1;
                        sda_drive_low <= 0;
                        scl_drive_low <= 0;
                        state <= IDLE;
                    end else if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        if (bit_index == 7) begin
                            bit_index <= 0;
                            state <= ACK_LOW;
                            scl_drive_low <= 1;
                            sda_drive_low <= 0;
                        end else begin
                            bit_index <= bit_index + 1'b1;
                            state <= BIT_LOW;
                            scl_drive_low <= 1;
                            sda_drive_low <= ~shift_byte[3'd6-bit_index];
                        end
                    end else phase_count <= phase_count + 1;
                end
                ACK_LOW: begin
                    scl_drive_low <= 1;
                    sda_drive_low <= 0;
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        state <= ACK_HIGH;
                        scl_drive_low <= 0;
                    end else phase_count <= phase_count + 1;
                end
                ACK_HIGH: begin
                    scl_drive_low <= 0;
                    if (!scl_in && MUTANT != 5) begin
                        phase_count <= phase_count;
                    end else if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        if (sda_in && MUTANT != 4) begin
                            ack_error <= 1;
                            state <= STOP_LOW;
                        end else if (byte_phase == 0 && repeated_latched) begin
                            state <= MUTANT == 3 ? STOP_LOW : REP_LOW;
                        end else if (byte_phase == 0 && !read_latched) begin
                            shift_byte <= MUTANT == 7 ? {write_latched[6:0], write_latched[7]} : write_latched;
                            byte_phase <= 1;
                            state <= BIT_LOW;
                        end else if (byte_phase == 1 && repeated_latched) begin
                            byte_phase <= 2;
                            state <= READ_LOW;
                        end else begin
                            state <= STOP_LOW;
                        end
                    end else phase_count <= phase_count + 1;
                end
                REP_LOW: begin
                    scl_drive_low <= 1;
                    sda_drive_low <= 0;
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        scl_drive_low <= 0;
                        state <= REP_HIGH;
                    end else phase_count <= phase_count + 1;
                end
                REP_HIGH: begin
                    if (scl_in) begin
                        sda_drive_low <= 1;
                        state <= REP_START;
                        phase_count <= 0;
                    end
                end
                REP_START: begin
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        shift_byte <= {address_latched, 1'b1};
                        byte_phase <= 1;
                        bit_index <= 0;
                        phase_count <= 0;
                        scl_drive_low <= 1;
                        state <= BIT_LOW;
                    end else phase_count <= phase_count + 1;
                end
                READ_LOW: begin
                    scl_drive_low <= 1;
                    sda_drive_low <= 0;
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        scl_drive_low <= 0;
                        state <= READ_HIGH;
                    end else phase_count <= phase_count + 1;
                end
                READ_HIGH: begin
                    if (!scl_in && MUTANT != 5) begin
                        phase_count <= phase_count;
                    end else if (phase_count == CLOCK_DIVIDER - 1) begin
                        read_shift[7-bit_index] <= MUTANT == 8 ? ~sda_in : sda_in;
                        phase_count <= 0;
                        if (bit_index == 7) begin
                            read_data <= (read_shift & 8'hFE) |
                                {7'b0, (MUTANT == 8 ? ~sda_in : sda_in)};
                            read_valid <= 1;
                            bit_index <= 0;
                            scl_drive_low <= 1;
                            state <= READ_NACK;
                        end else begin
                            bit_index <= bit_index + 1'b1;
                            scl_drive_low <= 1;
                            state <= READ_LOW;
                        end
                    end else phase_count <= phase_count + 1;
                end
                READ_NACK: begin
                    sda_drive_low <= 0;
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        state <= STOP_LOW;
                    end else phase_count <= phase_count + 1;
                end
                STOP_LOW: begin
                    scl_drive_low <= 1;
                    sda_drive_low <= 1;
                    if (phase_count == CLOCK_DIVIDER - 1) begin
                        phase_count <= 0;
                        scl_drive_low <= 0;
                        state <= STOP_HIGH;
                    end else phase_count <= phase_count + 1;
                end
                STOP_HIGH: begin
                    if (scl_in) begin
                        if (MUTANT == 2) begin
                            busy <= 0;
                            done <= 1;
                            state <= IDLE;
                        end else begin
                            sda_drive_low <= 0;
                            state <= STOP_RELEASE;
                        end
                    end
                end
                STOP_RELEASE: begin
                    busy <= 0;
                    done <= 1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

module memory_bounded_qualified #(
    parameter integer MUTANT = 0
) (
    input logic clk, input logic rst_n,
    input logic read_enable, input logic [2:0] read_address, output logic [15:0] read_data,
    input logic port0_request, input logic port0_write_enable, input logic [2:0] port0_address,
    input logic [15:0] port0_write_data, input logic [1:0] port0_byte_enable, output logic port0_grant,
    input logic port1_request, input logic port1_write_enable, input logic [2:0] port1_address,
    input logic [15:0] port1_write_data, input logic [1:0] port1_byte_enable, output logic port1_grant,
    input logic inject_single_error, input logic inject_double_error, input logic scrub_enable,
    output logic corrected_error, output logic uncorrectable_error, output logic scrub_done
);
    localparam integer DEPTH = 8;
    logic [15:0] storage [0:DEPTH-1];
    logic last_grant, accepted_write, selected_port;
    logic [2:0] selected_address;
    logic [15:0] selected_data, merged_word;
    logic [1:0] selected_byte_enable;
    integer index;

    always_comb begin
        port0_grant = 1'b0;
        port1_grant = 1'b0;
        if (port0_request && port0_write_enable && port1_request && port1_write_enable) begin
            if (last_grant) port0_grant = 1'b1;
            else port1_grant = 1'b1;
        end else if (port0_request && port0_write_enable) port0_grant = 1'b1;
        else if (port1_request && port1_write_enable) port1_grant = 1'b1;
        accepted_write = port0_grant || port1_grant;
        selected_port = port1_grant;
        selected_address = selected_port ? port1_address : port0_address;
        selected_data = selected_port ? port1_write_data : port0_write_data;
        selected_byte_enable = selected_port ? port1_byte_enable : port0_byte_enable;
        merged_word = storage[selected_address];
        if (selected_byte_enable[0]) merged_word[7:0] = selected_data[7:0];
        if (selected_byte_enable[1]) merged_word[15:8] = selected_data[15:8];
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            read_data <= '0;
            corrected_error <= 1'b0;
            uncorrectable_error <= 1'b0;
            scrub_done <= 1'b0;
            last_grant <= 1'b1;
            for (index = 0; index < DEPTH; index = index + 1) storage[index] <= 16'h0000;
        end else begin
            corrected_error <= 1'b0;
            uncorrectable_error <= 1'b0;
            scrub_done <= 1'b0;
            if (accepted_write) begin
                storage[selected_address] <= merged_word;
                last_grant <= selected_port;
            end
            if (read_enable) begin
                if (accepted_write && selected_address == read_address)
                    read_data <= merged_word;
                else if (MUTANT == 2 && inject_single_error)
                    read_data <= storage[read_address] ^ 16'h0001;
                else
                    read_data <= storage[read_address];
                corrected_error <= inject_single_error && MUTANT != 1;
                uncorrectable_error <= inject_double_error && MUTANT != 3;
                scrub_done <= inject_single_error && scrub_enable && MUTANT != 4;
                if (MUTANT == 5 && !inject_single_error && !inject_double_error)
                    corrected_error <= 1'b1;
            end
        end
    end
endmodule

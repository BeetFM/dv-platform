module memory_bounded_qualified #(
    parameter integer MUTANT = 0
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        read_enable,
    input  logic [2:0]  read_address,
    output logic [15:0] read_data,
    input  logic        port0_request,
    input  logic        port0_write_enable,
    input  logic [2:0]  port0_address,
    input  logic [15:0] port0_write_data,
    input  logic [1:0]  port0_byte_enable,
    output logic        port0_grant,
    input  logic        port1_request,
    input  logic        port1_write_enable,
    input  logic [2:0]  port1_address,
    input  logic [15:0] port1_write_data,
    input  logic [1:0]  port1_byte_enable,
    output logic        port1_grant,
    input  logic        inject_error,
    output logic        parity_error
);
    localparam integer DEPTH = 8;
    logic [15:0] storage [0:DEPTH-1];
    logic parity [0:DEPTH-1];
    logic last_grant;
    logic accepted_write;
    logic selected_port;
    logic [2:0] selected_address;
    logic [15:0] selected_data;
    logic [1:0] selected_byte_enable;
    logic [15:0] merged_word;
    integer index;

    always_comb begin
        port0_grant = 1'b0;
        port1_grant = 1'b0;
        if (port0_request && port0_write_enable && port1_request && port1_write_enable) begin
            if (MUTANT == 6) begin
                port0_grant = 1'b1;
                port1_grant = 1'b1;
            end else if (MUTANT == 3 || last_grant) begin
                port0_grant = 1'b1;
            end else begin
                port1_grant = 1'b1;
            end
        end else if (port0_request && port0_write_enable) begin
            port0_grant = 1'b1;
        end else if (port1_request && port1_write_enable) begin
            port1_grant = 1'b1;
        end

        accepted_write = port0_grant || port1_grant;
        selected_port = port1_grant;
        selected_address = selected_port ? port1_address : port0_address;
        selected_data = selected_port ? port1_write_data : port0_write_data;
        selected_byte_enable = selected_port ? port1_byte_enable : port0_byte_enable;
        merged_word = storage[selected_address];
        if (MUTANT == 1) begin
            merged_word = selected_data;
        end else begin
            if (selected_byte_enable[0])
                merged_word[7:0] = selected_data[7:0];
            if (selected_byte_enable[1])
                merged_word[15:8] = selected_data[15:8];
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            read_data <= '0;
            parity_error <= 1'b0;
            last_grant <= 1'b1;
            for (index = 0; index < DEPTH; index = index + 1) begin
                storage[index] <= (MUTANT == 4) ? 16'hffff : 16'h0000;
                parity[index] <= 1'b0;
            end
        end else begin
            if (accepted_write) begin
                if (!(MUTANT == 7 && selected_port)) begin
                    storage[selected_address] <= merged_word;
                    parity[selected_address] <= (MUTANT == 5) ? parity[selected_address] : ^merged_word;
                end
                last_grant <= selected_port;
            end
            if (read_enable) begin
                if (accepted_write && selected_address == read_address && MUTANT != 2)
                    read_data <= merged_word;
                else
                    read_data <= storage[read_address + ((MUTANT == 8) ? 3'd1 : 3'd0)];
                if (MUTANT == 5)
                    parity_error <= 1'b0;
                else
                    parity_error <= ((^storage[read_address]) ^ parity[read_address]) ^ inject_error;
            end else begin
                parity_error <= 1'b0;
            end
        end
    end
endmodule

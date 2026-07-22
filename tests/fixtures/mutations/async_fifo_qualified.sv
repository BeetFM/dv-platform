module async_fifo_qualified #(
    parameter integer DATA_WIDTH = 8,
    parameter integer ADDR_WIDTH = 2,
    parameter integer MUTANT = 0
) (
    input  logic                  wclk,
    input  logic                  wrst_n,
    input  logic                  w_en,
    input  logic [DATA_WIDTH-1:0] w_data,
    output logic                  full,
    output logic [ADDR_WIDTH:0]   w_ptr_bin,
    output logic [ADDR_WIDTH:0]   w_ptr_gray,
    output logic [ADDR_WIDTH:0]   r_gray_meta,
    output logic [ADDR_WIDTH:0]   r_gray_sync,
    input  logic                  rclk,
    input  logic                  rrst_n,
    input  logic                  r_en,
    output logic [DATA_WIDTH-1:0] r_data,
    output logic                  empty,
    output logic [ADDR_WIDTH:0]   r_ptr_bin,
    output logic [ADDR_WIDTH:0]   r_ptr_gray,
    output logic [ADDR_WIDTH:0]   w_gray_meta,
    output logic [ADDR_WIDTH:0]   w_gray_sync
);
    localparam integer DEPTH = 1 << ADDR_WIDTH;
    logic [DATA_WIDTH-1:0] storage [0:DEPTH-1];
    wire [ADDR_WIDTH:0] w_bin_next = w_ptr_bin + 1'b1;
    wire [ADDR_WIDTH:0] r_bin_next = r_ptr_bin + 1'b1;
    wire [ADDR_WIDTH:0] w_gray_next = (w_bin_next >> 1) ^ w_bin_next;
    wire [ADDR_WIDTH:0] r_gray_next = (r_bin_next >> 1) ^ r_bin_next;
    wire [ADDR_WIDTH-1:0] write_address = w_ptr_bin[ADDR_WIDTH-1:0] + (MUTANT == 1);
    wire [ADDR_WIDTH-1:0] read_address = r_ptr_bin[ADDR_WIDTH-1:0] + (MUTANT == 6);
    wire [ADDR_WIDTH:0] full_compare = {
        ~r_gray_sync[ADDR_WIDTH:ADDR_WIDTH-1], r_gray_sync[ADDR_WIDTH-2:0]
    };

    always_comb begin
        full = (w_ptr_gray == full_compare);
        empty = (r_ptr_gray == w_gray_sync);
        if (MUTANT == 3)
            empty = !empty;
    end

    always_ff @(posedge wclk or negedge wrst_n) begin
        if (!wrst_n) begin
            w_ptr_bin <= '0;
            w_ptr_gray <= '0;
            r_gray_meta <= '0;
            r_gray_sync <= '0;
        end else begin
            r_gray_meta <= r_ptr_gray;
            r_gray_sync <= (MUTANT == 5) ? (r_gray_meta ^ 3'b001) : r_gray_meta;
            if (w_en && (!full || MUTANT == 2)) begin
                storage[write_address] <= w_data;
                w_ptr_bin <= (MUTANT == 7 && &w_ptr_bin[ADDR_WIDTH-1:0]) ? w_ptr_bin : w_bin_next;
                w_ptr_gray <= (MUTANT == 4) ? w_bin_next : w_gray_next;
            end
        end
    end

    always_ff @(posedge rclk or negedge rrst_n) begin
        if (!rrst_n) begin
            r_ptr_bin <= '0;
            r_ptr_gray <= '0;
            w_gray_meta <= '0;
            w_gray_sync <= '0;
            r_data <= '0;
        end else begin
            w_gray_meta <= w_ptr_gray;
            w_gray_sync <= w_gray_meta;
            if (r_en && !empty) begin
                r_data <= storage[read_address];
                r_ptr_bin <= r_bin_next;
                r_ptr_gray <= r_gray_next;
            end
        end
    end
endmodule

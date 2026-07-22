module reset_domains_qualified #(
    parameter integer MUTANT = 0
) (
    input  logic src_clk,
    input  logic src_rst_n,
    input  logic power_good,
    output logic isolation_enable,
    output logic retention_enable,
    output logic src_release_meta,
    output logic src_ready,
    input  logic dst_clk,
    input  logic dst_rst_n,
    output logic dependency_meta,
    output logic dependency_sync,
    output logic dst_release_meta,
    output logic dst_release_ready,
    output logic dst_ready
);
    always_ff @(posedge src_clk or negedge src_rst_n) begin
        if (!src_rst_n) begin
            src_release_meta <= 1'b0;
            src_ready <= (MUTANT == 1);
        end else if (!power_good && MUTANT != 9) begin
            src_release_meta <= 1'b0;
            src_ready <= 1'b0;
        end else begin
            src_release_meta <= 1'b1;
            src_ready <= (MUTANT == 2) ? 1'b1 : src_release_meta;
        end
    end

    always_comb begin
        isolation_enable = !src_rst_n || !power_good || !src_ready;
        retention_enable = !src_rst_n || !power_good || !src_ready;
        if (MUTANT == 7)
            isolation_enable = 1'b0;
        if (MUTANT == 8)
            retention_enable = 1'b0;
    end

    always_ff @(posedge dst_clk or negedge dst_rst_n) begin
        if (!dst_rst_n) begin
            dependency_meta <= 1'b0;
            dependency_sync <= 1'b0;
            dst_release_meta <= 1'b0;
            dst_release_ready <= 1'b0;
        end else begin
            dependency_meta <= src_ready;
            dependency_sync <= (MUTANT == 4) ? !dependency_meta : dependency_meta;
            if (!dependency_sync && MUTANT != 3) begin
                dst_release_meta <= 1'b0;
                dst_release_ready <= 1'b0;
            end else begin
                dst_release_meta <= 1'b1;
                dst_release_ready <= (MUTANT == 5) ? 1'b1 : dst_release_meta;
            end
        end
    end

    always_comb begin
        dst_ready = dst_release_ready && dependency_sync;
        if (MUTANT == 3)
            dst_ready = dst_release_ready;
        if (MUTANT == 6 && !dst_rst_n)
            dst_ready = 1'b1;
    end
endmodule

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity broad_protocol_endpoints_vhdl is
    generic (MUTANT : integer := 0);
    port (
        clk : in std_logic;
        reset_n : in std_logic;
        x_awid : in std_logic_vector(3 downto 0); x_awaddr : in std_logic_vector(31 downto 0); x_awlen : in std_logic_vector(7 downto 0);
        x_awsize : in std_logic_vector(2 downto 0); x_awburst : in std_logic_vector(1 downto 0); x_awvalid : in std_logic; x_awready : out std_logic;
        x_wdata : in std_logic_vector(31 downto 0); x_wstrb : in std_logic_vector(3 downto 0); x_wlast : in std_logic; x_wvalid : in std_logic; x_wready : out std_logic;
        x_bid : out std_logic_vector(3 downto 0); x_bresp : out std_logic_vector(1 downto 0); x_bvalid : out std_logic; x_bready : in std_logic;
        x_arid : in std_logic_vector(3 downto 0); x_araddr : in std_logic_vector(31 downto 0); x_arlen : in std_logic_vector(7 downto 0);
        x_arsize : in std_logic_vector(2 downto 0); x_arburst : in std_logic_vector(1 downto 0); x_arvalid : in std_logic; x_arready : out std_logic;
        x_rid : out std_logic_vector(3 downto 0); x_rdata : out std_logic_vector(31 downto 0); x_rresp : out std_logic_vector(1 downto 0); x_rlast : out std_logic; x_rvalid : out std_logic; x_rready : in std_logic;
        wb_cyc : in std_logic; wb_stb : in std_logic; wb_we : in std_logic; wb_adr : in std_logic_vector(31 downto 0); wb_dat_w : in std_logic_vector(31 downto 0); wb_sel : in std_logic_vector(3 downto 0);
        wb_ack : out std_logic; wb_stall : out std_logic; wb_err : out std_logic; wb_rty : out std_logic; wb_dat_r : out std_logic_vector(31 downto 0); wb_cti : in std_logic_vector(2 downto 0); wb_bte : in std_logic_vector(1 downto 0);
        mm_read : in std_logic; mm_write : in std_logic; mm_address : in std_logic_vector(31 downto 0); mm_writedata : in std_logic_vector(31 downto 0); mm_byteenable : in std_logic_vector(3 downto 0); mm_burstcount : in std_logic_vector(7 downto 0);
        mm_waitrequest : out std_logic; mm_readdata : out std_logic_vector(31 downto 0); mm_readdatavalid : out std_logic; mm_writeresponsevalid : out std_logic; mm_response : out std_logic_vector(1 downto 0);
        ast_valid : in std_logic; ast_ready : out std_logic; ast_data : in std_logic_vector(31 downto 0); ast_startofpacket : in std_logic; ast_endofpacket : in std_logic; ast_empty : in std_logic_vector(1 downto 0); ast_channel : in std_logic_vector(3 downto 0); ast_error : in std_logic_vector(1 downto 0);
        h_hsel : in std_logic; h_haddr : in std_logic_vector(31 downto 0); h_htrans : in std_logic_vector(1 downto 0); h_hwrite : in std_logic; h_hsize : in std_logic_vector(2 downto 0); h_hburst : in std_logic_vector(2 downto 0); h_hwdata : in std_logic_vector(31 downto 0);
        h_hrdata : out std_logic_vector(31 downto 0); h_hready : out std_logic; h_hresp : out std_logic;
        tl_a_valid : in std_logic; tl_a_ready : out std_logic; tl_a_opcode : in std_logic_vector(2 downto 0); tl_a_param : in std_logic_vector(2 downto 0); tl_a_size : in std_logic_vector(3 downto 0); tl_a_source : in std_logic_vector(3 downto 0); tl_a_address : in std_logic_vector(31 downto 0); tl_a_mask : in std_logic_vector(3 downto 0); tl_a_data : in std_logic_vector(31 downto 0);
        tl_d_valid : out std_logic; tl_d_ready : in std_logic; tl_d_opcode : out std_logic_vector(2 downto 0); tl_d_param : out std_logic_vector(1 downto 0); tl_d_size : out std_logic_vector(3 downto 0); tl_d_source : out std_logic_vector(3 downto 0); tl_d_denied : out std_logic; tl_d_data : out std_logic_vector(31 downto 0); tl_d_corrupt : out std_logic
    );
end entity;

architecture rtl of broad_protocol_endpoints_vhdl is
    signal have_aw, have_w : std_logic := '0';
begin
    x_awready <= '0' when MUTANT = 1 else not have_aw and not x_bvalid;
    x_wready <= not have_w and not x_bvalid;
    x_arready <= not x_rvalid;
    wb_stall <= '0'; wb_ack <= '0' when MUTANT = 3 else wb_cyc and wb_stb; wb_err <= '0'; wb_rty <= '0'; wb_dat_r <= wb_adr xor x"55AAAA55";
    mm_waitrequest <= '0'; ast_ready <= '0' when MUTANT = 5 else '1'; h_hready <= '0' when MUTANT = 6 else '1'; h_hresp <= '0'; h_hrdata <= h_haddr xor x"A5A55A5A";
    tl_a_ready <= not tl_d_valid;

    process (clk, reset_n)
    begin
        if reset_n = '0' then
            have_aw <= '0'; have_w <= '0'; x_bvalid <= '0'; x_bid <= (others => '0'); x_bresp <= (others => '0');
            x_rvalid <= '0'; x_rid <= (others => '0'); x_rdata <= (others => '0'); x_rresp <= (others => '0'); x_rlast <= '0';
            mm_readdata <= (others => '0'); mm_readdatavalid <= '0'; mm_writeresponsevalid <= '0'; mm_response <= (others => '0');
            tl_d_valid <= '0'; tl_d_opcode <= (others => '0'); tl_d_param <= (others => '0'); tl_d_size <= (others => '0'); tl_d_source <= (others => '0'); tl_d_denied <= '0'; tl_d_data <= (others => '0'); tl_d_corrupt <= '0';
        elsif rising_edge(clk) then
            if x_awvalid = '1' and x_awready = '1' then have_aw <= '1'; x_bid <= x_awid; end if;
            if x_wvalid = '1' and x_wready = '1' then have_w <= '1'; end if;
            if have_aw = '1' and have_w = '1' then
                if MUTANT = 2 then x_bvalid <= '0'; else x_bvalid <= '1'; end if;
                have_aw <= '0'; have_w <= '0';
            end if;
            if x_bvalid = '1' and x_bready = '1' then x_bvalid <= '0'; end if;
            if x_arvalid = '1' and x_arready = '1' then x_rvalid <= '1'; x_rid <= x_arid; x_rdata <= x_araddr; x_rresp <= "00"; x_rlast <= '1'; end if;
            if x_rvalid = '1' and x_rready = '1' then x_rvalid <= '0'; end if;
            mm_readdatavalid <= '0' when MUTANT = 4 else mm_read; mm_writeresponsevalid <= mm_write;
            if mm_read = '1' then mm_readdata <= mm_address xor x"CAFEF00D"; end if;
            if tl_a_valid = '1' and tl_a_ready = '1' then
                if MUTANT = 7 then tl_d_valid <= '0'; else tl_d_valid <= '1'; end if;
                tl_d_opcode <= "001"; tl_d_size <= tl_a_size; tl_d_source <= tl_a_source; tl_d_data <= tl_a_data;
            end if;
            if tl_d_valid = '1' and tl_d_ready = '1' then tl_d_valid <= '0'; end if;
        end if;
    end process;
end architecture;

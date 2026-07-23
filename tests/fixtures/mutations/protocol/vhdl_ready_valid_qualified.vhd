library ieee;
use ieee.std_logic_1164.all;

entity vhdl_ready_valid_qualified is
    generic (
        MUTANT : natural := 0
    );
    port (
        clk       : in  std_logic;
        rst_n     : in  std_logic;
        in_valid  : in  std_logic;
        in_ready  : out std_logic;
        in_data   : in  std_logic_vector(7 downto 0);
        out_valid : out std_logic;
        out_ready : in  std_logic;
        out_data  : out std_logic_vector(7 downto 0)
    );
end entity;

architecture rtl of vhdl_ready_valid_qualified is
    signal full_q : std_logic;
    signal data_q : std_logic_vector(7 downto 0);
begin
    in_ready <= '0' when MUTANT = 2 else not full_q;
    out_valid <= '0' when MUTANT = 4 and out_ready = '0' else full_q;
    out_data <= not data_q when MUTANT = 3 else data_q;

    storage: process(clk, rst_n)
    begin
        if rst_n = '0' then
            full_q <= '1' when MUTANT = 1 else '0';
            data_q <= (others => '0');
        elsif rising_edge(clk) then
            if full_q = '1' and out_ready = '1' then
                full_q <= '0';
            elsif in_valid = '1' and full_q = '0' and MUTANT /= 2 then
                full_q <= '1';
                data_q <= in_data;
            end if;
        end if;
    end process;
end architecture;

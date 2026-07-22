library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity axi4_stream_profile_source_vhdl is
    generic (MUTANT : integer := 0);
    port (
        clk     : in  std_logic;
        reset_n : in  std_logic;
        tvalid  : out std_logic;
        tready  : in  std_logic;
        tdata   : out std_logic_vector(31 downto 0);
        tkeep   : out std_logic_vector(3 downto 0);
        tstrb   : out std_logic_vector(3 downto 0);
        tlast   : out std_logic;
        tid     : out std_logic_vector(3 downto 0);
        tdest   : out std_logic_vector(3 downto 0);
        tuser   : out std_logic_vector(3 downto 0)
    );
end entity;

architecture rtl of axi4_stream_profile_source_vhdl is
begin
    process (clk, reset_n)
    begin
        if reset_n = '0' then
            tvalid <= '0';
            tdata <= x"12345678";
            tkeep <= "1111";
            tstrb <= "1111";
            tlast <= '1';
            tid <= "0011";
            tdest <= "0101";
            tuser <= "0111";
        elsif rising_edge(clk) then
            if MUTANT = 1 then
                tvalid <= '0';
            else
                tvalid <= '1';
            end if;
            if MUTANT = 2 then
                tkeep <= "0000";
            end if;
            if MUTANT = 3 then
                tlast <= '0';
            end if;
            if MUTANT = 4 then
                tstrb <= "1111";
                tkeep <= "0011";
            end if;
        end if;
    end process;
end architecture;

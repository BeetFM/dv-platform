library ieee;
use ieee.std_logic_1164.all;

entity native_reset_register is
    port (
        clk    : in  std_logic;
        rst_n  : in  std_logic;
        data_o : out std_logic_vector(7 downto 0)
    );
end entity native_reset_register;

architecture rtl of native_reset_register is
begin
    register_process: process(clk, rst_n)
    begin
        if rst_n = '0' then
            data_o <= (others => '0');
        elsif rising_edge(clk) then
            data_o <= x"5a";
        end if;
    end process register_process;
end architecture rtl;

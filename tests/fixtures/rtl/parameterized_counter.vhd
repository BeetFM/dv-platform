library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity parameterized_counter is
    generic (
        WIDTH : positive := 8
    );
    port (
        clk     : in  std_logic;
        rst_n   : in  std_logic;
        enable  : in  std_logic;
        count_o : out std_logic_vector(WIDTH - 1 downto 0)
    );
end entity parameterized_counter;

architecture rtl of parameterized_counter is
    signal count_q : unsigned(WIDTH - 1 downto 0);
begin
    counter_process: process(clk, rst_n)
    begin
        if rst_n = '0' then
            count_q <= (others => '0');
        elsif rising_edge(clk) then
            if enable = '1' then
                count_q <= count_q + 1;
            end if;
        end if;
    end process counter_process;

    count_o <= std_logic_vector(count_q);
end architecture rtl;

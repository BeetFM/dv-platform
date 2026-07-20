library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity dv_qualification is
end entity;

architecture test of dv_qualification is
begin
  process
    variable left_value  : unsigned(3 downto 0) := to_unsigned(3, 4);
    variable right_value : unsigned(3 downto 0) := to_unsigned(5, 4);
  begin
    assert left_value + right_value = to_unsigned(8, 4)
      report "qualification arithmetic failed"
      severity failure;
    report "dv-platform qualification passed" severity note;
    wait;
  end process;
end architecture;

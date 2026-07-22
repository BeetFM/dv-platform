library ieee;
use ieee.std_logic_1164.all;

package typed_generated_types is
    subtype word_t is std_logic_vector(7 downto 0);
    type control_t is record
        enable : std_logic;
        value  : word_t;
    end record;
    type word_array_t is array (natural range <>) of word_t;
end package;

library ieee;
use ieee.std_logic_1164.all;
use work.typed_generated_types.all;

entity typed_generated is
    generic (WIDTH : positive := 8);
    port (
        clk     : in std_logic;
        control : in control_t;
        samples : in word_array_t(0 to 3);
        result  : out word_t
    );
end entity;

architecture rtl of typed_generated is
begin
    lanes: for index in 0 to 1 generate
        result <= samples(index);
    end generate;
    wide: if WIDTH >= 8 generate
        result <= control.value;
    end generate;
end architecture;

module gpio_timer_interrupt_qualified #(
    parameter integer MUTANT = 0
) (
    input  logic       clock,
    input  logic       reset,
    input  logic [3:0] gpio_input,
    output logic [3:0] gpio_output,
    output logic [3:0] gpio_output_enable,
    input  logic       gpio_write,
    input  logic [3:0] gpio_write_data,
    input  logic [3:0] gpio_write_mask,
    input  logic [3:0] gpio_set,
    input  logic [3:0] gpio_clear,
    input  logic [3:0] gpio_direction,
    input  logic [3:0] gpio_rise_enable,
    input  logic [3:0] gpio_fall_enable,
    input  logic [3:0] gpio_level_enable,
    output logic [3:0] gpio_irq_pending,
    input  logic [3:0] gpio_irq_clear,
    input  logic       timer_enable,
    input  logic [7:0] timer_prescaler,
    input  logic [7:0] timer_compare,
    input  logic       timer_periodic,
    output logic [7:0] timer_count,
    output logic       timer_irq,
    input  logic       timer_irq_clear,
    input  logic       watchdog_enable,
    input  logic       watchdog_feed,
    input  logic [7:0] watchdog_timeout,
    output logic       watchdog_irq,
    output logic       watchdog_reset,
    input  logic       pwm_enable,
    input  logic [7:0] pwm_period,
    input  logic [7:0] pwm_duty,
    input  logic       pwm_polarity,
    output logic       pwm_output,
    input  logic [3:0] interrupt_sources,
    input  logic [3:0] interrupt_mask,
    input  logic [3:0] interrupt_clear,
    output logic [3:0] interrupt_pending,
    input  logic       interrupt_ack,
    output logic [1:0] interrupt_active,
    output logic       interrupt_valid
);
    logic [3:0] previous_gpio;
    logic [7:0] timer_prescale_count;
    logic [7:0] watchdog_count;
    logic [7:0] pwm_count;

    always_comb begin
        gpio_output_enable = MUTANT == 1 ? ~gpio_direction : gpio_direction;
        pwm_output = pwm_enable ? ((pwm_count < pwm_duty) ^ pwm_polarity) : pwm_polarity;
        interrupt_valid = MUTANT == 10 ? 1'b0 : |interrupt_pending;
        if (interrupt_pending[0]) interrupt_active = 0;
        else if (interrupt_pending[1]) interrupt_active = MUTANT == 9 ? 2 : 1;
        else if (interrupt_pending[2]) interrupt_active = 2;
        else interrupt_active = 3;
    end

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) begin
            gpio_output <= 0;
            previous_gpio <= 0;
            gpio_irq_pending <= 0;
        end else begin
            previous_gpio <= gpio_input;
            if (gpio_write)
                gpio_output <= MUTANT == 2 ? gpio_write_data :
                    ((gpio_output & ~gpio_write_mask) | (gpio_write_data & gpio_write_mask));
            if (|gpio_set) gpio_output <= MUTANT == 3 ? gpio_output : gpio_output | gpio_set;
            if (|gpio_clear) gpio_output <= gpio_output & ~gpio_clear;
            gpio_irq_pending <= (
                (gpio_irq_pending & ~gpio_irq_clear) |
                ((~previous_gpio & gpio_input) & gpio_rise_enable) |
                ((previous_gpio & ~gpio_input) & gpio_fall_enable) |
                (gpio_input & gpio_level_enable)
            );
            if (MUTANT == 4) gpio_irq_pending <= 0;
        end
    end

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) begin
            timer_count <= 0;
            timer_prescale_count <= 0;
            timer_irq <= 0;
        end else begin
            if (timer_irq_clear) timer_irq <= 0;
            if (!timer_enable) begin
                timer_count <= 0;
                timer_prescale_count <= 0;
            end else if (timer_prescale_count >= timer_prescaler) begin
                timer_prescale_count <= 0;
                if (timer_count + 1 >= timer_compare) begin
                    if (MUTANT != 5) timer_irq <= 1;
                    timer_count <= timer_periodic ? 0 : timer_count + 1'b1;
                end else timer_count <= timer_count + 1'b1;
            end else timer_prescale_count <= timer_prescale_count + 1'b1;
        end
    end

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) begin
            watchdog_count <= 0;
            watchdog_irq <= 0;
            watchdog_reset <= 0;
        end else if (!watchdog_enable) begin
            watchdog_count <= 0;
            watchdog_irq <= 0;
            watchdog_reset <= 0;
        end else if (watchdog_feed && MUTANT != 6) begin
            watchdog_count <= 0;
        end else if (watchdog_count + 1 >= watchdog_timeout) begin
            watchdog_irq <= 1;
            watchdog_reset <= MUTANT == 7 ? 1'b0 : 1'b1;
        end else watchdog_count <= watchdog_count + 1'b1;
    end

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) pwm_count <= 0;
        else if (!pwm_enable || pwm_period == 0) pwm_count <= 0;
        else if (pwm_count + 1 >= pwm_period)
            pwm_count <= MUTANT == 8 ? pwm_count : 0;
        else pwm_count <= pwm_count + 1'b1;
    end

    always_ff @(posedge clock or negedge reset) begin
        if (!reset) interrupt_pending <= 0;
        else begin
            interrupt_pending <= (interrupt_pending | (interrupt_sources & interrupt_mask)) & ~interrupt_clear;
            if (interrupt_ack)
                interrupt_pending[interrupt_active] <= 1'b0;
        end
    end
endmodule

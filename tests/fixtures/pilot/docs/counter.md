# Pilot counter requirements

The `event_counter` uses `phase` as its clock. The active-high `clear_n` reset
clears `result` to zero. The counter increments `result` when `request` is
asserted and holds `result` when `request` is low.

The `pilot_top` connects `system_clk`, `system_reset`, `request`, and `result`
to its `event_counter` child instance without changing their interface meaning.

The `stream_buffer` and `pilot_top` expose input and output ready/valid
channels. A transfer is accepted only when `in_valid` and `in_ready` are both
asserted. Accepted `in_data` appears unchanged on `out_data` with `out_valid`
within three cycles. While `out_valid` is asserted and `out_ready` is low, the
buffer holds `out_valid` and `out_data` stable until the transfer is accepted.

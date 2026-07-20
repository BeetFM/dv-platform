# Transfer rules

AXI4-Lite transfers occur on `VALID && READY` independently per channel. APB4
uses setup followed by access and completes on `PSEL && PENABLE && PREADY`.
Backpressure, stability, wait states, and errors must be represented explicitly.

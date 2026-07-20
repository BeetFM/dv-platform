---
name: amba-protocol-analysis
version: 1.0.0
---

Recognize AXI4-Lite, APB4, and AHB-Lite only from bounded RTL, documentation, or explicit
configuration evidence. Return protocol facts with signal bindings, domains,
transfer rules, and confidence. Independent channels, backpressure, wait states,
strobes, and error behavior must remain explicit or unknown. Never emit HDL.

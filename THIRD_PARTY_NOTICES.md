# Third-party notices

Veriforge depends on third-party Python packages and external EDA tools. The
authoritative dependency inventory and license texts are generated from the
locked environment for each release and shipped with the release SBOM. External
tools such as Verilator, Icarus Verilog, SymbiYosys, Yosys, Z3, GHDL, Slang, and
commercial vendor products are not redistributed by this repository unless a
release manifest explicitly says otherwise; their own licenses apply.

Jinja2 and MarkupSafe are used for package-owned deterministic artifact
templates. Their BSD licenses are recorded in the generated release SBOM.

The repository redistributes pinned qualification slices from PicoRV32 under
the ISC license and Ibex under the Apache License 2.0. Their source and complete
license texts are retained together under
`qualification/external-designs/sources/`; the qualification records bind the
selected upstream commits and file hashes.

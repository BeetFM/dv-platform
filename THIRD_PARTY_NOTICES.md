# Third-party notices

The matrix benchmark under `qualification/fixtures/tpu/` comes from LogikBench
via the pinned OpenROAD-flow-scripts revision in its `upstream.json`. The original
Zero ASIC copyright notices and `LICENSES/LogikBench-MIT.txt` are retained. The
benchmark name describes a TPU-style matrix tile; it is not Google TPU IP.

The AES benchmark under `qualification/fixtures/aes/` originates from OpenCores
via OpenROAD-flow-scripts. Its pinned revision and file hashes are recorded in
`upstream.json`. The upstream LICENSE and source copyright notices are retained;
redistributions of source, netlist, binary, and silicon must preserve the applicable
notices and disclaimer.

The locked Python dependency inventory and licenses are exported by `scripts/release/sbom.py`. Optional AI execution uses LiteLLM and Tenacity; their transitive dependencies retain their own licenses.

OpenROAD, OpenSTA, Yosys, and OpenSSL are separately provisioned tools. Their licenses apply to their use and distribution.

The SKY130 workflow separately provisions Magic, KLayout, Netgen, and the public SkyWater/open_pdks assets. Pinned source and PDK archive identities are in `src/dv_platform/sky130-pin.json`. Their upstream licenses and notices remain in the downloaded sources and technology archives; these tool binaries and foundry assets are not bundled into the Python distributions.

The retained GCD/Nangate45 qualification assets originate from the OpenROAD repository revision recorded in `qualification/policies/openroad-fixture-v1.json`. Preserve upstream copyright and license notices in source assets and evidence.

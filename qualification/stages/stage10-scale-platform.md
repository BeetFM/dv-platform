# Stage 10 scale and platform qualification

Status: accepted on 2026-07-22 for commit
`ebb28cd75b24442d3c728fc31eedc9fc5178c6d4` and wheel SHA-256
`93ce9ad8c867078191d97536e4b5d4aa60b0f9a16c03b197ed8cc42a8b3ef501`.

The identical deterministic workload contains 2,000,000 RTL lines, a
134,217,728-byte XML document, and a 67,109,418-byte PDF. Input SHA-256
identities match on both platforms. Baseline and current records were produced
from clean worktrees with `PYTHONHASHSEED=0` and validated by
`scripts/qualification/performance.py --require-ga-scale`.

- WSL2 Ubuntu 24.04 used kernel `6.6.114.1-microsoft-standard-WSL2`.
- Native Ubuntu 24.04.4 ran in a KVM guest on kernel `6.8.0-134-generic`.
- Both per-platform current runs remain within the 10% runtime and peak-RSS
  regression limit.
- The Ubuntu container preflight was not accepted as native evidence because it
  correctly reported the shared WSL2 kernel.

The four performance-qualification v2 records are checked in adjacent to this
document and are revalidated by `tests/qualification/test_performance_qualification.py`.

The platform gate also includes `oci-sandbox-runtime-v1.json`, bound to clean
commit `9b6cb79995730aca2928368db5c36b32ce8c9486` and immutable Ubuntu 24.04 image
digest `sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90`.
The live Docker 29.5.2 probe verifies a non-root container UID, network denial,
read-only root and source mounts, an isolated writable output, dropped
capabilities, no-new-privileges, CPU/memory/PID limits, and explicit environment
allowlisting. The host Docker daemon is not rootless; the qualified product
claim is unprivileged sandbox execution, while Podman `keep-id` remains the
rootless-daemon deployment path.

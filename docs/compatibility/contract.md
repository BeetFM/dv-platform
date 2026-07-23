# Refactor compatibility contract

The maximum-simplification refactor is gated by a deterministic compatibility
fingerprint. The contract covers:

- all symbols and callable signatures at the legacy `agent`, `analysis`, `core`,
  `generators`, `run`, CLI, and enterprise module paths;
- dataclass fields and legacy class lookup modules;
- main and enterprise CLI help, invalid-command exit behavior, stdout, and
  stderr;
- console scripts and plugin entry-point targets;
- persisted schema and adapter API versions; and
- paths, kinds, sizes, and SHA-256 hashes for representative artifacts from
  every built-in generation target.

Temporary roots, repository roots, timestamps, UUIDs, revision IDs, and run IDs
are normalized before hashing. The complete normalized manifest can be
inspected without changing the baseline:

```bash
uv run python scripts/compatibility_contract.py --manifest
```

CI and local refactor checkpoints compare against
`docs/compatibility-baseline.json`:

```bash
uv run python scripts/compatibility_contract.py --check
```

An intentional compatibility change requires an explicit product decision and
review of the full manifest before updating the baseline. Moving implementation
code behind an existing facade must not require a baseline update.

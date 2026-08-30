# Planeon MAS Harness Contracts

`planeon-harness-contracts` is the public contract authority for the Planeon
Enterprise Multi-Agent-System Harness Platform. This first bootstrap contains a
typed Python package shell, empty registry and validation APIs, a closed
`harnessctl` command loader, deterministic package construction, and offline
verification infrastructure.

No domain schema, compiler behavior, network client, deployable service, cloud
resource, paid provider, or API key is included in `CON-001`.

## Requirements

- CPython 3.12
- GNU Make
- `uv` with Python downloads disabled
- A local, pre-populated toolchain for air-gapped execution

The package has no runtime or build dependencies. Its PEP 517 backend is part of
the source tree and writes byte-reproducible wheel and sdist archives.

## Offline verification

Packet acceptance is intentionally not run as a collection of ad-hoc commands.
The trusted runner sets `HARNESS_TASK_PACKET` to the hash-pinned `CON-001` YAML
authority and invokes only:

```text
./ci/verify-offline.sh
```

That wrapper proves OS-enforced outbound denial, hides the packet path and
sensitive environment from children, runs the packet's prefetch and acceptance
argv in one process tree, and rechecks the packet digest after every command.
CI uses only the preinstalled root-owned launcher on a credential-free ephemeral
self-hosted runner. It uploads no artifact and uses no remote cache.

The common developer targets are `make prefetch`, `make zero-bill`, `make test`,
`make typecheck`, and `make build`. Every target delegates to the closed JSON
descriptor dispatcher; no target embeds a shell command string.

## Public bootstrap API

```python
from planeon_harness_contracts import ContractRegistry, ValidationResult

registry = ContractRegistry.empty()
result = registry.validate("ExampleKind", {})
assert isinstance(result, ValidationResult)
assert not result.accepted
```

No contract kind is registered yet. `CON-002` is the sole owner of the initial
taxonomy/catalog kinds and the `validate` and `catalog` command registrations.

## Evidence boundaries

A source commit, green CI check, merge, built package, signature, deployment,
runtime observation, assurance result, and tenant acceptance are independent
states. This bootstrap produces only source, offline test, and local package
digest evidence. It does not claim a published artifact, deployment, runtime,
assurance certification, or tenant acceptance.

## License and security

The project is Apache-2.0 licensed. See `SECURITY.md` for private vulnerability
reporting guidance and `CONTRIBUTING.md` for packet-scoped contribution rules.


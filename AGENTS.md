# Sol-High Product Execution Rules

1. Implement exactly one approved task packet per branch and pull request.
2. Change only that packet's repository-local `allowedPaths`.
3. Read the packet's complete predecessor contracts before editing.
4. Never mount, open, receive, or modify a warm-start checkout during product
   implementation. Historical source provenance is not copy authorization.
5. Do not add cloud provisioning, hosted runners, paid or metered providers,
   third-party API keys, runtime downloads, mutable artifacts, remote caches, or
   external telemetry defaults.
6. Run acceptance only through the packet's exact `offlineExecution.wrapperArgv`
   with its hash-pinned YAML authority, in one deny-all-outbound process tree.
7. Preserve source, CI, merge, artifact, deployment, runtime, assurance, and
   tenant acceptance as separate evidence states.
8. `CON-001` is the sole owner of `Makefile`, `ci/run_make_target.py`, the generic
   `harnessctl` loader, and the inert `PORTING.yaml` bootstrap. Later packets may
   not edit those paths unless their approved packet explicitly grants the path.
9. Later Make-using packets add only `ci/targets/<lowercase-packet-id>.json` and
   later command owners add only their declared command descriptors and handlers.
10. A future source port requires a revised `PORT_CANDIDATE` packet, path-level
    legal approval, an authorization ID, an exact mapping, and the corresponding
    `PORTING.yaml` record. Until then its `records` array stays empty.
11. Use the packet's exact `codex/*` branch, open a pull request, monitor the
    ephemeral self-hosted check, fix bounded failures, and merge only when green.


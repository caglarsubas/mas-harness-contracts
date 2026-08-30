# Contributing

Changes are accepted only through an approved task packet from the public
Harness Onion engineering repository. Before coding, confirm the packet's
repository, branch, predecessors, `allowedPaths`, exclusions, offline commands,
evidence, and rollback boundary.

Use one `codex/<packet-id>-<slug>` branch and one pull request per packet. Do not
combine refactors or future packet work. Acceptance must run through the signed
offline launcher and the pull request must remain green on the credential-free
ephemeral self-hosted runner before merge.

Source reuse is deny-by-default. Do not read or copy any warm-start checkout in
an implementation run. Report a needed public-contract, isolation, licensing,
destructive-data, or billing-boundary decision before changing it.


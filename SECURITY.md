# Security Policy

Please do not publish vulnerability details in a pull request or public issue.
Use GitHub's private vulnerability reporting for this repository when enabled,
or contact the maintainers through an agreed private channel.

Reports should include affected commit or release, reproducible steps, impact,
and whether tenant isolation, signature custody, offline execution, or the
zero-bill boundary is involved. Do not include production credentials, tenant
data, API keys, or live exploit payloads.

The `CON-001` bootstrap has no network client, service, credential integration,
or tenant data path. A green source check is not deployment or runtime evidence.


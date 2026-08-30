#!/usr/bin/env python3
"""Fail unless the trusted OS sandbox denies an outbound TCP connection."""

from __future__ import annotations

import errno
import os
import socket
import sys

EXPECTED_DENIAL_ERRNOS = {
    "darwin-sandbox": {errno.EACCES, errno.EPERM},
    "linux-firejail": {errno.EACCES, errno.EPERM, errno.ENETUNREACH, errno.EHOSTUNREACH},
}


def denial_is_proven(backend: str, result: int | None) -> bool:
    """Return true only for a backend-specific OS denial result."""

    return result in EXPECTED_DENIAL_ERRNOS.get(backend, set())


def main() -> int:
    """Attempt one fixed egress connection and require kernel denial."""

    backend = os.environ.get("HARNESS_OFFLINE_BACKEND", "")
    if backend not in EXPECTED_DENIAL_ERRNOS:
        print("offline network canary refused: recognized isolation backend required", file=sys.stderr)
        return 2
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(0.5)
            result = client.connect_ex(("1.1.1.1", 443))
    except OSError as exc:
        result = exc.errno
    if denial_is_proven(backend, result):
        print(f"offline network canary: {backend} denied outbound egress with errno={result}")
        return 0
    print(
        f"offline network canary failed: backend={backend!r} errno={result}; OS denial was not proven",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


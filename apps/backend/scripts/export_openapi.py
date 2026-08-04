"""Write the API's OpenAPI document to disk.

The schema is generated from the running application rather than maintained by
hand, so it cannot drift from the endpoints. Committing the output makes an API
change visible in review as a diff, and gives client generators a stable input
that does not require a running server.

Usage:
    python scripts/export_openapi.py [destination]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from truvix.main import create_app
from truvix.shared.config import (
    DatabaseSettings,
    Environment,
    ObservabilitySettings,
    RedisSettings,
    SecuritySettings,
    Settings,
)

DEFAULT_DESTINATION = Path("docs/openapi.json")

# Generating the schema only builds routes; no connection is opened, so these
# values exist purely to satisfy validation.
_PLACEHOLDER_DSN = "postgresql+asyncpg://truvix:truvix@localhost:5432/truvix"
_PLACEHOLDER_REDIS = "redis://localhost:6379/0"
_PLACEHOLDER_KEY = "openapi-export-only-key-not-used-for-signing"


def build_document() -> dict[str, object]:
    """Generate the OpenAPI document for the current API surface."""
    settings = Settings(
        _env_file=None,
        environment=Environment.DEVELOPMENT,
        database=DatabaseSettings(dsn=_PLACEHOLDER_DSN, _env_file=None),
        redis=RedisSettings(dsn=_PLACEHOLDER_REDIS, _env_file=None),
        security=SecuritySettings(secret_key=_PLACEHOLDER_KEY, _env_file=None),
        observability=ObservabilitySettings(log_level="ERROR", _env_file=None),
    )
    document: dict[str, object] = create_app(settings).openapi()
    return document


def main(argv: list[str]) -> int:
    """Write the document and report where it went.

    Args:
        argv: Command line arguments after the program name.

    Returns:
        A process exit code.
    """
    destination = Path(argv[0]) if argv else DEFAULT_DESTINATION
    destination.parent.mkdir(parents=True, exist_ok=True)

    document = build_document()
    # Sorted keys and a trailing newline keep the committed file diff-stable
    # across regenerations.
    destination.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    paths = document.get("paths", {})
    endpoint_count = len(paths) if isinstance(paths, dict) else 0
    print(f"Wrote {endpoint_count} paths to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

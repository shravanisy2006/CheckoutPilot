"""
Export the backend's API description (OpenAPI) to docs/openapi.json.

    python -m scripts.export_openapi

Used for API docs and SDK generation (for example with APIMatic, see docs/apimatic.md).
Run it again whenever an endpoint changes.
"""

import json
import sys
from pathlib import Path

OUT = Path("docs/openapi.json")


def main() -> int:
    from backend.main import app

    spec = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(spec['paths'])} endpoints, OpenAPI {spec['openapi']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

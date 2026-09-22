"""Dump the OpenAPI spec without starting the server.

`create_app` builds the routes but does not run the lifespan, so no checkpoint
is loaded and this needs neither a GPU nor a HuggingFace download.

    python -m laya_serve.openapi > clients/typescript/openapi.json
"""

import json
import sys

from .api import create_app
from .config import Settings


def main() -> None:
    spec = create_app(Settings()).openapi()
    json.dump(spec, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

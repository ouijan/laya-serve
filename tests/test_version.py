"""One version across the server, the image and the client.

A `v<semver>` tag publishes the Docker image and the npm client together, so
a consumer can pin `ghcr.io/ouijan/laya-serve:0.2.0` against
`@ouijan/laya-client@0.2.0` and know they match. That only holds if the
manifests agree, which is what these check.
"""

import json
from pathlib import Path

from laya_serve import __version__

ROOT = Path(__file__).resolve().parents[1]
CLIENT_PACKAGE = ROOT / "clients/typescript/package.json"


def client_version() -> str:
    return json.loads(CLIENT_PACKAGE.read_text())["version"]


def test_client_version_matches_the_server():
    assert client_version() == __version__, (
        f"clients/typescript/package.json is {client_version()} but the "
        f"package is {__version__}; bump both or the published image and "
        "client will not line up"
    )


def test_openapi_reports_the_package_version():
    from laya_serve.api import create_app
    from laya_serve.config import Settings

    assert create_app(Settings()).openapi()["info"]["version"] == __version__

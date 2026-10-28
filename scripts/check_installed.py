"""Installed-wheel acceptance without an API key, Node.js or provider connection."""

import socket
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import policydesk
from policydesk.server import create_app


def main() -> None:
    package = Path(policydesk.__file__).resolve().parent
    assert "site-packages" in package.parts, "Run with the clean installed-wheel interpreter"
    web = package / "web_dist"
    assert (web / "index.html").is_file()
    connect = socket.socket.connect

    def local_only(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return connect(sock, address)
        raise AssertionError("Installed check forbids external connections")

    socket.socket.connect = local_only
    socket.getaddrinfo = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("DNS forbidden")
    )
    with tempfile.TemporaryDirectory(prefix="policydesk-wheel-") as temporary:
        with TestClient(
            create_app(None, data_dir=Path(temporary) / ".runtime"),
            base_url="http://127.0.0.1:8765",
        ) as client:
            config = client.get("/api/config").json()
            assert config["enabled"] is False
            assert config["session_budget"]["spent_usd"] == "0"
            index = client.get("/policydesk/")
            assert index.status_code == 200
            assert 'name="policydesk-runtime" content="local"' in index.text
            for asset in (web / "assets").iterdir():
                response = client.get(f"/policydesk/assets/{asset.name}")
                assert response.status_code == 200
                assert response.content == asset.read_bytes()
    print(
        "Installed wheel verified: bundled frontend, loopback app, inert startup, no key/Node/provider request"
    )


if __name__ == "__main__":
    main()

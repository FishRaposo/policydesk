"""Exercise installed package resources and actions while denying outbound sockets."""

import socket
import tempfile
from pathlib import Path

from policydesk.evaluation import evaluate_split
from policydesk.fixtures import cases, orders, ticket_for
from policydesk.models import TODAY
from policydesk.openai_client import NetworkModeDisabled, ReplayClient
from policydesk.pipeline import run
from policydesk.store import Store


def denied(*args, **kwargs):
    raise AssertionError("Outbound network is forbidden in this runtime check")


def main() -> None:
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.socket.sendto = denied
    socket.create_connection = denied
    with tempfile.TemporaryDirectory(prefix="policydesk-offline-") as temporary:
        path = Path(temporary)
        for split in ("dev", "heldout"):
            assert evaluate_split(split, path / "reports")["failed"] == 0
        store = Store(path / "runtime.db")
        try:
            store.seed(orders())
            result = run(ticket_for(cases()[0]), store, ReplayClient(), TODAY)
            assert (
                store.approve(result["pending_actions"][0]["id"], "offline-check", TODAY)[
                    "executed"
                ]
                is False
            )
        finally:
            store.close()
        for mode in ("record", "live"):
            try:
                ReplayClient(mode=mode)
            except NetworkModeDisabled:
                continue
            raise AssertionError("Network mode was not rejected")
    print(
        "Offline runtime verified: 60 synthetic cases, SQLite authorization, and no outbound sockets"
    )


if __name__ == "__main__":
    main()

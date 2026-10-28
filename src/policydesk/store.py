"""Local SQLite audit and simulated authorization; no external actions."""

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .models import Decision, Order
from .resources import canonical, digest, load_policy


class StaleApproval(ValueError):
    pass


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL, step TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pending_actions (
                id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, order_id TEXT NOT NULL,
                action TEXT NOT NULL, context TEXT NOT NULL, binding_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', approved_by TEXT, approved_at TEXT);
        """)

    def close(self) -> None:
        self.connection.close()

    def seed(self, orders: list[Order]) -> None:
        with self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO orders VALUES (?, ?)",
                [(o.order_id, o.model_dump_json()) for o in orders],
            )

    def put_order(self, order: Order) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO orders VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (order.order_id, order.model_dump_json()),
            )

    def lookup(self, order_id: str, customer_id: str) -> tuple[str, Order | None]:
        row = self.connection.execute(
            "SELECT payload FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if row is None:
            return "not_found", None
        order = Order.model_validate_json(row["payload"])
        if order.customer_id != customer_id:
            return "ownership_denied", None
        return "found", order

    def recent(self, customer_id: str) -> list[Order]:
        return sorted(
            [
                o
                for row in self.connection.execute("SELECT payload FROM orders")
                if (o := Order.model_validate_json(row["payload"])).customer_id == customer_id
            ],
            key=lambda o: (o.estimated_delivery, o.order_id),
            reverse=True,
        )

    def audit(self, ticket_id: str, step: str, payload: Any) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO audit_log(ticket_id,step,payload,created_at) VALUES (?,?,?,?)",
                (ticket_id, step, canonical(payload), datetime.now(UTC).isoformat()),
            )

    def create_pending(
        self, ticket_id: str, order: Order, decision: Decision, customer_id: str, today: date
    ) -> list[dict[str, Any]]:
        if decision.outcome != "approve":
            return []
        context = {
            "customer_id": customer_id,
            "order": order.model_dump(mode="json"),
            "actions": [a.model_dump(mode="json") for a in decision.actions],
            "policy": load_policy(),
            "today": today.isoformat(),
        }
        binding = digest(context)
        ids: list[str] = []
        with self.connection:
            for index, action in enumerate(context["actions"]):
                action_id = digest({"ticket": ticket_id, "binding": binding, "index": index})[:24]
                ids.append(action_id)
                self.connection.execute(
                    """INSERT OR IGNORE INTO pending_actions
                    (id,ticket_id,order_id,action,context,binding_hash) VALUES(?,?,?,?,?,?)""",
                    (
                        action_id,
                        ticket_id,
                        order.order_id,
                        canonical(action),
                        canonical(context),
                        binding,
                    ),
                )
        return [
            dict(
                self.connection.execute(
                    "SELECT id,action,status,binding_hash FROM pending_actions WHERE id=?", (i,)
                ).fetchone()
            )
            for i in ids
        ]

    def approve(self, action_id: str, actor: str, today: date) -> dict[str, Any]:
        if not actor.strip() or len(actor) > 80:
            raise ValueError("A local operator label is required")
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                "SELECT * FROM pending_actions WHERE id=?", (action_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Unknown pending action")
            context = json.loads(row["context"])
            status, order = self.lookup(row["order_id"], context["customer_id"])
            current = {
                **context,
                "order": order.model_dump(mode="json") if order else None,
                "policy": load_policy(),
                "today": today.isoformat(),
            }
            if (
                status != "found"
                or digest(current) != row["binding_hash"]
                or json.loads(row["action"]) not in context["actions"]
                or row["status"] not in ("pending", "approved")
            ):
                self.connection.execute(
                    "UPDATE pending_actions SET status='stale' WHERE id=?", (action_id,)
                )
                stale = True
            else:
                stale = False
                if row["status"] == "pending":
                    self.connection.execute(
                        "UPDATE pending_actions SET status='approved',approved_by=?,approved_at=? WHERE id=?",
                        (actor, datetime.now(UTC).isoformat(), action_id),
                    )
                    self.connection.execute(
                        "INSERT INTO audit_log(ticket_id,step,payload,created_at) VALUES(?,?,?,?)",
                        (
                            row["ticket_id"],
                            "approval",
                            canonical({"id": action_id, "actor": actor, "executed": False}),
                            datetime.now(UTC).isoformat(),
                        ),
                    )
        if stale:
            raise StaleApproval("Action is stale; re-evaluate the changed order, policy or date")
        return {
            "id": action_id,
            "status": "approved",
            "executed": False,
            "already_approved": row["status"] == "approved",
        }

    def history(self) -> list[dict[str, Any]]:
        return [
            {**dict(row), "payload": json.loads(row["payload"])}
            for row in self.connection.execute("SELECT * FROM audit_log ORDER BY id")
        ]

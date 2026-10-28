"""Local CLI; model network modes are deliberately unavailable."""

import json
import os
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from .fixtures import cases, orders, ticket_for
from .models import TODAY, Language, Ticket
from .openai_client import ReplayClient
from .pipeline import run as run_pipeline
from .store import Store

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
DB = Path(".runtime/policydesk.sqlite")
DbOption = Annotated[Path, typer.Option(help="Local SQLite path (simulated actions only)")]


def output(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))


def today() -> date:
    return date.fromisoformat(os.environ.get("POLICYDESK_TODAY", TODAY.isoformat()))


def execute(ticket: Ticket, db: Path) -> None:
    client = ReplayClient()
    store = Store(db)
    try:
        store.seed(orders())
        output(run_pipeline(ticket, store, client, today()))
    finally:
        store.close()


@app.command()
def init(db: DbOption = DB) -> None:
    """Initialize fictional orders in a local database."""
    store = Store(db)
    try:
        store.seed(orders())
        output({"db": str(db), "provenance": "synthetic", "executed": False})
    finally:
        store.close()


@app.command()
def demo(
    case: Annotated[str, typer.Option(help="Dev scenario ID")] = "D-PT-01", db: DbOption = DB
) -> None:
    """Run a committed synthetic dev ticket through the Python pipeline."""
    match = next((c for c in cases() if c["id"] == case), None)
    if match is None:
        raise typer.BadParameter("Unknown dev case; choose list-cases")
    execute(ticket_for(match), db)


@app.command()
def list_cases() -> None:
    """List available development replay inputs."""
    output(
        [{key: c[key] for key in ("id", "lang", "customer_id", "message", "tags")} for c in cases()]
    )


@app.command()
def run(
    message: str,
    customer: Annotated[str, typer.Option()],
    language: Annotated[Language, typer.Option()] = "pt",
    db: DbOption = DB,
) -> None:
    """Replay an exact known input; unknown text raises CassetteMissing."""
    execute(Ticket(message=message, customer_id=customer, language=language), db)


@app.command()
def approve(
    action_id: str, actor: Annotated[str, typer.Option()] = "demo-operator", db: DbOption = DB
) -> None:
    """Record local authorization only; executes no external action."""
    store = Store(db)
    try:
        output(store.approve(action_id, actor, today()))
    finally:
        store.close()


@app.command()
def report(db: DbOption = DB) -> None:
    """Read the local audit history."""
    store = Store(db)
    try:
        output(store.history())
    finally:
        store.close()


@app.command(name="eval")
def evaluate(
    split: Annotated[str, typer.Option()] = "heldout",
    baseline: Annotated[bool, typer.Option()] = False,
    output_dir: Annotated[Path, typer.Option()] = Path(".runtime/reports"),
) -> None:
    """Run synthetic regression cases, not a model benchmark."""
    if baseline:
        raise typer.BadParameter(
            "Real-model baseline comparison is unavailable in this synthetic prototype"
        )
    from .evaluation import evaluate_split

    result = evaluate_split(split, output_dir)
    output(result)
    if result["failed"]:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

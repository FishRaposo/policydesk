"""Loopback-only recruiter app. Keys never enter its HTTP contract."""

import asyncio
import json
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .fixtures import cases, orders, ticket_for
from .models import TODAY, Order, Ticket
from .resources import canonical, digest
from .store import StaleApproval, Store

ORIGIN = "http://127.0.0.1:8765"
VERIFICATION = (
    "OpenAI integration implemented; live verification and empirical results not yet performed."
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceInput(Contract):
    ticket: Ticket
    order: Order | None = None


class RunInput(Contract):
    kind: Literal["ticket", "comparison"] = "ticket"
    revision: int = Field(ge=0)
    model: Literal["gpt-6-luna", "gpt-6.1-terra"] = "gpt-6-luna"
    max_cost_usd: str = Field(default="0.05", max_length=64)
    session_limit_usd: str = Field(default="1.00", max_length=64)
    record: bool = False
    confirm_spend: Literal[True]
    idempotency_key: str = Field(min_length=1, max_length=100)

    @field_validator("max_cost_usd", "session_limit_usd")
    @classmethod
    def valid_budget(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Invalid allowance") from exc
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Allowance must be positive and finite")
        return value


class ApprovalInput(Contract):
    revision: int = Field(ge=0)
    run_id: str


class Runtime:
    def __init__(self, api_key: str | None, data_dir: Path, provider_factory: Any):
        from .telemetry import SessionBudget

        self.__key = api_key
        self.enabled = bool(api_key)
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.factory = provider_factory
        self.csrf = secrets.token_urlsafe(32)
        self.session = SessionBudget(Decimal("1.00"))
        self.revision = 0
        self.ticket = ticket_for(cases()[0])
        self.order: Order | None = next(
            (
                o
                for o in orders()
                if o.order_id in self.ticket.message and o.customer_id == self.ticket.customer_id
            ),
            None,
        )
        self.jobs: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.submissions: dict[str, tuple[str, str]] = {}
        self.active: str | None = None

    def safe(self, value: Any) -> Any:
        if isinstance(value, str):
            if self.__key:
                value = value.replace(self.__key, "[REDACTED]")
            return re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)
        if isinstance(value, dict):
            return {
                self.safe(k): self.safe(v)
                for k, v in value.items()
                if k.lower() not in {"api_key", "authorization", "headers"}
            }
        if isinstance(value, (list, tuple)):
            return [self.safe(v) for v in value]
        return value

    def config(self) -> dict[str, Any]:
        from .telemetry import LIVE_LIMITS, model_profiles

        profiles = model_profiles()
        for profile in profiles:
            profile.setdefault("id", profile.get("model", profile.get("name")))
            profile.setdefault("label", profile["id"])
        fixture_orders = orders()
        return self.safe(
            {
                "csrf_token": self.csrf,
                "enabled": self.enabled,
                "models": profiles,
                "limits": LIVE_LIMITS,
                "session_budget": self.session.summary(),
                "workspace_revision": self.revision,
                "workspace": {
                    "ticket": self.ticket.model_dump(mode="json"),
                    "order": self.order.model_dump(mode="json") if self.order else None,
                },
                "fictional_customers": [
                    {"customer_id": c, "label": f"Fictional customer {c}"}
                    for c in sorted({o.customer_id for o in fixture_orders})
                ],
                "orders": [o.model_dump(mode="json") for o in fixture_orders],
                "verification_status": VERIFICATION,
            }
        )

    def edit(self, workspace: WorkspaceInput) -> dict[str, int]:
        originals = {o.order_id: o for o in orders()}
        if workspace.ticket.customer_id not in {o.customer_id for o in originals.values()}:
            raise HTTPException(422, "Unknown fictional customer")
        if workspace.order:
            original = originals.get(workspace.order.order_id)
            if (
                not original
                or original.customer_id != workspace.ticket.customer_id
                or workspace.order.customer_id != original.customer_id
            ):
                raise HTTPException(422, "Order identity is fixed and must belong to this customer")
            try:
                workspace.order.validate_date(TODAY)
            except ValueError as exc:
                raise HTTPException(422, "Invalid fictional order dates") from exc
        self.ticket = workspace.ticket.model_copy(
            update={"message": self.safe(workspace.ticket.message)}
        )
        self.order = workspace.order
        return self.invalidate()

    def invalidate(self) -> dict[str, int]:
        """Revoke before parsing edited facts, including malformed browser input."""
        self.revision += 1
        for job in self.jobs.values():
            job["stale"] = True
            if job["db"].is_file():
                stale_store = Store(job["db"])
                try:
                    stale_store.invalidate_authorizations()
                finally:
                    stale_store.close()
            if job["status"] in ("queued", "running"):
                job["cancel_requested"] = True
        return {"revision": self.revision}

    def view(self, job_id: str) -> dict[str, Any]:
        if job_id not in self.jobs:
            raise HTTPException(404, "Unknown run")
        return self.safe(
            {k: v for k, v in self.jobs[job_id].items() if k not in {"db", "cancel_requested"}}
        )

    def start(self, options: RunInput) -> dict[str, Any]:
        if not self.enabled:
            raise HTTPException(409, "Live mode is disabled; launch with --enable-live")
        request_hash = digest(options.model_dump(mode="json"))
        prior = self.submissions.get(options.idempotency_key)
        if prior:
            if prior[0] != request_hash:
                raise HTTPException(409, "Submission key already used for different inputs")
            return self.view(prior[1])
        if self.active is not None:
            raise HTTPException(409, "Another run is active in this local session")
        if options.revision != self.revision:
            raise HTTPException(409, "Workspace changed; review current inputs")
        try:
            self.session.set_limit(Decimal(options.session_limit_usd))
        except ValueError as exc:
            raise HTTPException(
                409, "Session allowance cannot cover existing reservations"
            ) from exc
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "status": "queued",
            "revision": self.revision,
            "stale": False,
            "progress": [],
            "result": None,
            "error_code": None,
            "cancel_requested": False,
            "db": self.data_dir / f"{job_id}.sqlite",
        }
        self.jobs[job_id] = job
        self.submissions[options.idempotency_key] = (request_hash, job_id)
        self.active = job_id
        self.tasks[job_id] = asyncio.create_task(
            self.execute(
                job_id,
                options,
                self.ticket.model_copy(deep=True),
                self.order.model_copy(deep=True) if self.order else None,
            )
        )
        return self.view(job_id)

    async def execute(
        self, job_id: str, options: RunInput, ticket: Ticket, order: Order | None
    ) -> None:
        from .live import OpenAIProvider

        job = self.jobs[job_id]
        provider = None
        store = None
        try:
            job["status"] = "running"
            factory = self.factory or OpenAIProvider
            key = self.__key
            if not key:
                raise RuntimeError("Live key is unavailable")
            provider = factory(api_key=key, session=self.session, model=options.model)

            def cancelled() -> bool:
                return bool(job["cancel_requested"])

            def progress(value: dict[str, Any]) -> None:
                job["progress"].append(self.safe(value))

            if options.kind == "comparison":
                from .benchmark import compare

                result = await compare(
                    provider,
                    output_dir=self.data_dir / job_id,
                    repeats=3,
                    max_cost_usd=Decimal(options.max_cost_usd),
                    cancelled=cancelled,
                    progress=progress,
                    record_dir=self.data_dir / "recordings" if options.record else None,
                )
            else:
                store = Store(job["db"])
                store.seed(orders())
                if order:
                    store.put_order(order)
                result = await provider.run(
                    ticket,
                    store,
                    today=TODAY,
                    max_cost_usd=Decimal(options.max_cost_usd),
                    record_dir=self.data_dir / "recordings" if options.record else None,
                    cancelled=cancelled,
                    progress=progress,
                )
            job["result"] = self.safe(result)
            if (job["stale"] or cancelled()) and store:
                # An active worker may have produced actions after an earlier edit.
                store.invalidate_authorizations()
                job["result"]["pending_actions"] = []
            status = result.get("status", "completed")
            job["status"] = (
                "cancelled"
                if cancelled()
                else status
                if status in {"completed", "failed", "cancelled", "budget_exceeded"}
                else "completed"
            )
            job["error_code"] = result.get("error_code")
            (self.data_dir / f"{job_id}.json").write_text(
                canonical(self.view(job_id)) + "\n", encoding="utf-8", newline="\n"
            )
        except asyncio.CancelledError:
            job["status"] = "cancelled"
        except Exception:
            # SDK exceptions can carry HTTP details; never reflect them to a browser.
            job["status"] = "failed"
            job["error_code"] = "local_run_failed"
        finally:
            if store:
                if job["status"] != "completed":
                    store.invalidate_authorizations()
                store.close()
            if provider:
                try:
                    await provider.aclose()
                except Exception:
                    pass
            if self.active == job_id:
                self.active = None

    async def shutdown(self) -> None:
        for job in self.jobs.values():
            job["cancel_requested"] = True
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.__key = None


def create_app(
    api_key: str | None,
    *,
    data_dir: Path,
    provider_factory: Any = None,
    web_dir: Path | None = None,
) -> FastAPI:
    runtime = Runtime(api_key, data_dir, provider_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await runtime.shutdown()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.runtime = runtime

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.headers.get("host") != "127.0.0.1:8765":
            return JSONResponse({"error_code": "invalid_host"}, status_code=400)
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("origin") != ORIGIN or not secrets.compare_digest(
                request.headers.get("X-PolicyDesk-CSRF", ""), runtime.csrf
            ):
                return JSONResponse({"error_code": "invalid_local_origin_or_csrf"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return JSONResponse({"error_code": "json_required"}, status_code=415)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"error_code": "invalid_content_length"}, status_code=400)
        if length < 0:
            return JSONResponse({"error_code": "invalid_content_length"}, status_code=400)
        if length > 100_000:
            return JSONResponse({"error_code": "request_too_large"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'none'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return JSONResponse({"error_code": "invalid_request"}, status_code=422)

    @app.get("/api/config")
    async def config():
        return runtime.config()

    @app.post("/api/workspace")
    async def workspace(value: WorkspaceInput):
        return runtime.edit(value)

    @app.post("/api/workspace/invalidate")
    async def invalidate(value: Contract):
        return runtime.invalidate()

    @app.post("/api/runs", status_code=202)
    async def start(value: RunInput):
        return runtime.start(value)

    @app.get("/api/runs/{job_id}")
    async def job(job_id: str):
        return runtime.view(job_id)

    @app.post("/api/runs/{job_id}/cancel")
    async def cancel(job_id: str):
        runtime.view(job_id)
        value = runtime.jobs[job_id]
        value["cancel_requested"] = True
        if value["status"] == "completed":
            value["status"] = "cancelled"
            if value["db"].is_file():
                cancelled_store = Store(value["db"])
                try:
                    cancelled_store.invalidate_authorizations()
                finally:
                    cancelled_store.close()
            if value["result"]:
                value["result"]["pending_actions"] = []
        return {"id": job_id, "cancel_requested": True, "billing_reversal_guaranteed": False}

    @app.post("/api/budget/acknowledge")
    async def acknowledge():
        if runtime.active:
            raise HTTPException(409, "Wait for the active run to finish")
        runtime.session.acknowledge_unknown()
        return runtime.session.summary()

    @app.post("/api/approvals/{action_id}")
    async def approve(action_id: str, value: ApprovalInput):
        runtime.view(value.run_id)
        job = runtime.jobs[value.run_id]
        if (
            value.revision != runtime.revision
            or job["revision"] != runtime.revision
            or job["stale"]
            or job["status"] != "completed"
        ):
            raise HTTPException(409, "Inputs changed; re-evaluate before authorization")
        if not any(
            a.get("id") == action_id for a in (job["result"] or {}).get("pending_actions", [])
        ):
            raise HTTPException(404, "Unknown pending action")
        store = Store(job["db"])
        try:
            return store.approve(action_id, "local-demo-operator", TODAY)
        except (StaleApproval, ValueError) as exc:
            raise HTTPException(409, "Stale authorization") from exc
        finally:
            store.close()

    @app.get("/api/runs/{job_id}/report")
    async def report(job_id: str, format: Literal["json", "md"] = "json"):
        value = runtime.view(job_id)
        if format == "json":
            return Response(
                canonical(value) + "\n",
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="policydesk-{job_id}.json"'},
            )
        body = (
            "# PolicyDesk local run\n\n"
            + VERIFICATION
            + "\n\nFictional data. Estimated costs are not invoice totals.\n\n```json\n"
            + json.dumps(value, ensure_ascii=False, indent=2)
            + "\n```\n"
        )
        return Response(
            body,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="policydesk-{job_id}.md"'},
        )

    static = web_dir or Path(__file__).parent / "web_dist"

    @app.get("/")
    async def home():
        return Response(status_code=307, headers={"Location": "/policydesk/"})

    @app.get("/policydesk/{path:path}")
    async def frontend(path: str):
        candidate = (static / (path or "index.html")).resolve()
        if not candidate.is_relative_to(static.resolve()) or not candidate.is_file():
            raise HTTPException(
                404, "Frontend missing; use the release wheel or build the frontend"
            )
        if candidate.name == "index.html":
            html = candidate.read_text(encoding="utf-8").replace(
                "<head>", '<head><meta name="policydesk-runtime" content="local">', 1
            )
            return HTMLResponse(html)
        return FileResponse(candidate)

    return app

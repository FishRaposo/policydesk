"""Opt-in OpenAI Responses adapter. Construction is inert; only run/baseline send requests.

ReplayClient and its synthetic protocol deliberately remain separate. Injected HTTP transports
are marked as mocks and cannot produce authentic-provider evidence.
"""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from . import prompts
from .evaluation import source_hash
from .models import (
    TODAY,
    Decision,
    DraftReply,
    Extraction,
    LookupOrderArguments,
    Order,
    Ticket,
    Violation,
)
from .policy import evaluate
from .replies import render
from .resources import canonical, digest
from .store import Store
from .telemetry import (
    LIVE_LIMITS,
    BudgetExceeded,
    SessionBudget,
    model_profiles,
    positive,
    pricing,
    profile_for,
    usage_cost,
    worst_cost,
)
from .validators import check

__all__ = ["OpenAIProvider", "model_profiles", "replay_recording"]


class WorkflowStop(Exception):
    def __init__(self, code: str, status: str = "failed"):
        self.code, self.status = code, status
        super().__init__(code)


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _disable_provider_logging() -> None:
    """Never log SDK request bodies, credentials or inferred headers in this app.

    OPENAI_LOG=debug enables payload logging in SDK 2.54.0. Disable these library
    namespaces and existing descendants without changing the environment or
    unrelated application loggers. New lazy-import descendants inherit the level.
    """
    namespaces = ("openai", "httpx", "httpcore")
    names = set(namespaces) | {
        name
        for name in tuple(logging.Logger.manager.loggerDict)
        if any(name.startswith(namespace + ".") for namespace in namespaces)
    }
    for name in names:
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL + 1)
        logger.disabled = True
        logger.propagate = False


def _scrub(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            _scrub(name, key): _scrub(item, key)
            for name, item in value.items()
            if name.casefold() not in ("authorization", "api_key", "headers")
        }
    if isinstance(value, list):
        return [_scrub(item, key) for item in value]
    if isinstance(value, str):
        if key:
            value = value.replace(key, "[REDACTED]")
        return re.sub(r"\bsk-[A-Za-z0-9_-]{6,}", "[REDACTED]", value)
    return value


@dataclass
class RunContext:
    cap: Decimal
    cancelled: Callable[[], bool] | None
    progress: Callable[[dict], None] | None
    started: float = field(default_factory=perf_counter)
    measured_at: str = field(default_factory=timestamp)
    run_id: str = field(default_factory=lambda: uuid4().hex)
    calls: list[dict[str, Any]] = field(default_factory=list)
    captures: list[dict[str, Any]] = field(default_factory=list)
    spent: Decimal = Decimal(0)
    unknown: bool = False
    generations: int = 0

    def guard(self) -> float:
        if self.cancelled and self.cancelled():
            raise WorkflowStop("cancelled", "cancelled")
        remaining = LIVE_LIMITS["pipeline_deadline_seconds"] - (perf_counter() - self.started)
        if remaining <= 0:
            raise WorkflowStop("workflow_deadline")
        return min(float(LIVE_LIMITS["request_timeout_seconds"]), remaining)

    def emit(self, step: str) -> None:
        if self.progress:
            self.progress(
                {
                    "step": step,
                    "generation_requests": self.generations,
                    "estimated_cost_usd": str(self.spent),
                    "unknown_cost": self.unknown,
                }
            )


class OpenAIProvider:
    def __init__(
        self, api_key: str, session: SessionBudget, model: str = "gpt-6-luna", transport=None
    ):
        # Optional imports keep the synthetic-only install usable without the live extra.
        import httpx
        from openai import AsyncOpenAI
        from openai import __version__ as sdk_version

        _disable_provider_logging()
        if not api_key or not isinstance(api_key, str):
            raise ValueError("An explicitly supplied API key is required")
        self.model, self.profile, self.session = model, profile_for(model), session
        self.sdk_version, self._source_hash = sdk_version, source_hash()
        self.provenance = "mock_openai_transport" if transport is not None else "openai_live"
        self._key = api_key  # memory only, used to redact opt-in captures
        http = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=LIVE_LIMITS["request_timeout_seconds"],
        )
        self._client = AsyncOpenAI(
            api_key=api_key,
            admin_api_key="",
            organization="",
            project="",
            webhook_secret="",
            base_url="https://api.openai.com/v1",
            http_client=http,
            max_retries=0,
            timeout=LIVE_LIMITS["request_timeout_seconds"],
        )
        # SDK 2.54.0 unconditionally merges OPENAI_CUSTOM_HEADERS at construction.
        # Discard the inferred mapping before any request; only the supplied key
        # may authorize this client. Raw HTTP tests bind this pinned-SDK private
        # invariant, including mixed-case Authorization keys. No environment mutation.
        self._client._custom_headers = {}

    async def aclose(self) -> None:
        await self._client.close()
        self._client.api_key = ""
        self._key = ""

    def benchmark_metadata(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provenance": self.provenance,
            "prompt_version": prompts.VERSION,
            "sdk_version": self.sdk_version,
            "source_hash": self._source_hash,
            "settings": {
                **LIVE_LIMITS,
                "store": False,
                "reasoning": "low",
                "max_retries": 0,
                "cache_mode": "implicit",
                "cache_ttl": "30m",
                "service_tier": "default",
            },
            "pricing": pricing(),
        }

    async def _generate(
        self,
        ctx: RunContext,
        step: str,
        history: list[dict[str, Any]],
        instructions: str,
        text: dict[str, Any],
        tools: bool,
    ) -> dict[str, Any]:
        ctx.guard()
        if ctx.generations >= LIVE_LIMITS["max_generation_requests"]:
            raise WorkflowStop("generation_limit")
        if self.session.summary()["blocked"]:
            raise WorkflowStop("unknown_usage_unacknowledged", "budget_exceeded")
        common: dict[str, Any] = {
            "model": self.model,
            "input": history,
            "instructions": instructions,
            "text": text,
            "reasoning": {"effort": "low"},
            "truncation": "disabled",
        }
        if tools:
            common.update(tools=prompts.TOOLS, parallel_tool_calls=False, tool_choice="auto")
        count_request_snapshot = deepcopy(common)
        attempt_metadata = {
            "requested_model": self.model,
            "returned_model": None,
            "requested_service_tier": None,
            "returned_service_tier": None,
            "sdk_version": self.sdk_version,
            "prompt_version": prompts.VERSION,
            "prompt_hash": digest(instructions),
            "schema_hash": digest(text["format"]["schema"]),
            "source_hash": self._source_hash,
            "request_id": None,
            "http_status": None,
        }
        count_started = perf_counter()
        count_call: dict[str, Any] = {
            **attempt_metadata,
            "kind": "input_token_count",
            "step": step,
            "started_at": timestamp(),
            "status": "failed",
            "estimated_cost_usd": "0",
            "unknown_cost": False,
        }
        ctx.calls.append(count_call)
        try:
            async with asyncio.timeout(ctx.guard()):
                count = await self._client.responses.input_tokens.count(**common)
            tokens = count.input_tokens
            if type(tokens) is not int or tokens < 0:
                raise ValueError("Invalid token count")
            count_call.update(status="completed", input_tokens=tokens)
            counted_raw = count.model_dump(mode="json")
            count_call.update(
                returned_model=counted_raw.get("model"),
                returned_service_tier=counted_raw.get("service_tier"),
                request_id=getattr(count, "_request_id", None),
            )
            ctx.captures.append(
                {
                    "kind": "input_token_count",
                    "request": count_request_snapshot,
                    "response": counted_raw,
                }
            )
        except asyncio.CancelledError:
            count_call["error_code"] = "cancelled"
            raise WorkflowStop("cancelled", "cancelled") from None
        except Exception as exc:
            count_call.update(
                request_id=getattr(exc, "request_id", None),
                http_status=getattr(exc, "status_code", None),
            )
            count_call["error_code"] = "token_count_failed"
            raise WorkflowStop("token_count_failed") from None
        finally:
            count_call.update(
                api_round_trip_ms=(perf_counter() - count_started) * 1000, finished_at=timestamp()
            )
        ctx.guard()
        if tokens > LIVE_LIMITS["max_input_tokens"]:
            raise WorkflowStop("input_token_limit")
        reservation_cost = worst_cost(self.profile, tokens, LIVE_LIMITS["max_output_tokens"])
        if ctx.spent + reservation_cost > ctx.cap:
            raise WorkflowStop("run_budget_exceeded", "budget_exceeded")
        try:
            reservation = self.session.reserve(reservation_cost)
        except BudgetExceeded:
            raise WorkflowStop("session_budget_exceeded", "budget_exceeded") from None
        request = {
            **common,
            "store": False,
            "max_output_tokens": LIVE_LIMITS["max_output_tokens"],
            "include": ["reasoning.encrypted_content"],
            "service_tier": "default",
            "prompt_cache_options": {"mode": "implicit", "ttl": "30m"},
        }
        generation_request_snapshot = deepcopy(request)
        started = perf_counter()
        call: dict[str, Any] = {
            **attempt_metadata,
            "requested_service_tier": request["service_tier"],
            "kind": "generation",
            "step": step,
            "model": self.model,
            "started_at": timestamp(),
            "status": "failed",
            "reserved_usd": str(reservation_cost),
            "usage": None,
            "estimated_cost_usd": None,
            "unknown_cost": False,
        }
        ctx.calls.append(call)
        ctx.generations += 1
        settled = False
        try:
            ctx.emit(step)
            async with asyncio.timeout(ctx.guard()):
                response = await self._client.responses.create(**request)
            raw = response.model_dump(mode="json", exclude_unset=True, warnings=False)
            ctx.captures.append(
                {"kind": "generation", "request": generation_request_snapshot, "response": raw}
            )
            call["response_id"] = raw.get("id")
            call["request_id"] = response._request_id
            call["usage"] = raw.get("usage")
            call.update(
                returned_model=raw.get("model"), returned_service_tier=raw.get("service_tier")
            )
            # A selected profile cannot price an unexpected model/tier or omitted billing
            # metadata. Preserve the full reservation until the user acknowledges it.
            if raw.get("model") != self.profile["id"] or raw.get("service_tier") != "default":
                raise WorkflowStop("unexpected_billing_profile")
            try:
                cost = usage_cost(self.profile, raw.get("usage") or {})
            except (KeyError, ValueError, TypeError, ArithmeticError):
                raise WorkflowStop("unknown_provider_usage") from None
            self.session.settle(reservation, cost)
            settled = True
            ctx.spent += cost
            call.update(estimated_cost_usd=str(cost), status="completed")
            if ctx.spent > ctx.cap or cost > reservation_cost:
                raise WorkflowStop("provider_usage_exceeds_reservation", "budget_exceeded")
            ctx.guard()
            if raw.get("status") != "completed":
                raise WorkflowStop("incomplete_response")
            return raw
        except WorkflowStop as exc:
            call["error_code"] = exc.code
            raise
        except asyncio.CancelledError:
            call["error_code"] = "cancelled"
            raise WorkflowStop("cancelled", "cancelled") from None
        except Exception as exc:
            # No provider usage was received. Even authentication/quota rejections keep
            # an unknown reservation rather than reporting an invented zero charge.
            call.update(
                http_status=getattr(exc, "status_code", None),
                request_id=getattr(exc, "request_id", None),
            )
            call["error_code"] = "provider_request_failed"
            raise WorkflowStop("provider_request_failed") from None
        finally:
            if not settled:
                self.session.mark_unknown(reservation)
                ctx.unknown = True
                call["unknown_cost"] = True
            call.update(
                api_round_trip_ms=(perf_counter() - started) * 1000, finished_at=timestamp()
            )

    @staticmethod
    def _structured(raw: dict[str, Any]) -> dict[str, Any]:
        outputs = raw.get("output")
        if not isinstance(outputs, list) or any(not isinstance(item, dict) for item in outputs):
            raise ValueError("Invalid response output array")
        content = [
            part
            for item in outputs
            if item.get("type") == "message"
            for part in item.get("content", [])
        ]
        if any(not isinstance(part, dict) for part in content):
            raise ValueError("Invalid message content array")
        if any(part.get("type") == "refusal" for part in content):
            raise WorkflowStop("provider_refusal")
        texts = [part["text"] for part in content if part.get("type") == "output_text"]
        if len(texts) != 1:
            raise ValueError("Exactly one structured reply is required")
        result = json.loads(texts[0])
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object")
        return result

    async def run(
        self,
        ticket: Ticket,
        store: Store,
        *,
        today: date = TODAY,
        max_cost_usd: Decimal = Decimal("0.05"),
        record_dir: Path | None = None,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[dict], None] | None = None,
        create_actions: bool = True,
    ) -> dict:
        return await self._run(
            ticket,
            store,
            today,
            max_cost_usd,
            record_dir,
            cancelled,
            progress,
            create_actions,
            baseline=False,
        )

    async def baseline(
        self,
        ticket: Ticket,
        store: Store,
        *,
        today: date = TODAY,
        max_cost_usd: Decimal = Decimal("0.05"),
        record_dir: Path | None = None,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[dict], None] | None = None,
        create_actions: bool = False,
    ) -> dict:
        # Baseline proposals are never persisted, even if a caller accidentally opts in.
        return await self._run(
            ticket,
            store,
            today,
            max_cost_usd,
            record_dir,
            cancelled,
            progress,
            False,
            baseline=True,
        )

    async def _run(
        self,
        ticket: Ticket,
        store: Store,
        today: date,
        cap: Decimal,
        record_dir: Path | None,
        cancelled,
        progress,
        create_actions: bool,
        *,
        baseline: bool,
    ) -> dict[str, Any]:
        positive(cap)
        if record_dir is not None:
            record_dir = record_dir.resolve()
            if ".runtime" not in record_dir.parts:
                raise ValueError("Captures must be explicitly placed under a .runtime directory")
        ctx = RunContext(cap, cancelled, progress)
        ticket_id = ctx.run_id
        trace: list[dict[str, Any]] = []
        extraction: Extraction | None = None
        order: Order | None = None
        decision = Decision(
            outcome="needs_human", actions=[], clause_ids=["XX-0"], reasons=["workflow_failed"]
        )
        final: DraftReply | None = None
        violations: list[Violation] = []
        pending: list[dict[str, Any]] = []
        repair_attempted = False
        status, error_code = "completed", None
        tool_count = 0
        seen: dict[str, Order] = {}
        ambiguous = False
        denied = False
        structured: dict[str, Any] = {}
        seen_call_ids: set[str] = set()
        history: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": canonical(
                    {"ticket": ticket.model_dump(mode="json"), "today": today.isoformat()}
                ),
            }
        ]
        if baseline:
            history = [
                {
                    "role": "user",
                    "content": canonical(
                        {
                            "ticket": ticket.model_dump(mode="json"),
                            "today": today.isoformat(),
                            "authorized_orders": [
                                o.model_dump(mode="json") for o in store.recent(ticket.customer_id)
                            ],
                        }
                    ),
                }
            ]
        try:
            while True:
                raw = await self._generate(
                    ctx,
                    "baseline" if baseline else "extract",
                    history,
                    prompts.BASELINE if baseline else prompts.EXTRACT,
                    prompts.BASELINE_FORMAT if baseline else prompts.EXTRACT_FORMAT,
                    not baseline,
                )
                outputs = raw.get("output", [])
                if not isinstance(outputs, list) or any(
                    not isinstance(item, dict) for item in outputs
                ):
                    raise WorkflowStop("invalid_provider_output")
                calls = [item for item in outputs if item.get("type") == "function_call"]
                if baseline and calls:
                    raise WorkflowStop("baseline_tool_call_forbidden")
                if not calls:
                    structured = self._structured(raw)
                    break
                history.extend(outputs)  # includes encrypted reasoning, never previous_response_id
                if tool_count + len(calls) > LIVE_LIMITS["max_tool_calls"]:
                    raise WorkflowStop("tool_limit")
                for call in calls:
                    ctx.guard()
                    tool_count += 1
                    call_id = call.get("call_id")
                    if not isinstance(call_id, str) or not call_id or call_id in seen_call_ids:
                        raise WorkflowStop("invalid_tool_call_id")
                    seen_call_ids.add(call_id)
                    args = json.loads(call["arguments"])
                    if call["name"] == "lookup_order":
                        arguments = LookupOrderArguments.model_validate(args)
                        lookup_status, candidate = store.lookup(
                            arguments.order_id, ticket.customer_id
                        )
                        denied = denied or lookup_status == "ownership_denied"
                        if candidate:
                            seen[candidate.order_id] = candidate
                        result = {
                            "status": lookup_status,
                            "order": candidate.model_dump(mode="json") if candidate else None,
                        }
                    elif call["name"] == "list_recent_orders" and args == {}:
                        recent = store.recent(ticket.customer_id)
                        ambiguous = ambiguous or len(recent) != 1
                        if len(recent) == 1:
                            seen[recent[0].order_id] = recent[0]
                        result = {
                            "status": "ambiguous" if ambiguous else "found",
                            "orders": [o.model_dump(mode="json") for o in recent],
                        }
                    else:
                        raise WorkflowStop("invalid_tool_arguments")
                    trace.append(
                        {"step": call["name"], "status": result["status"], "call_id": call_id}
                    )
                    history.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": canonical(result),
                        }
                    )
                if denied:
                    decision = Decision(
                        outcome="needs_human",
                        actions=[],
                        clause_ids=["ID-1"],
                        reasons=["ownership_denied"],
                    )
                    final = render(decision, ticket.language)
                    break
            if not denied:
                if baseline:
                    if set(structured) != {"decision", "reply"}:
                        raise ValueError("Invalid baseline envelope")
                    decision = Decision.model_validate(structured["decision"])
                    final = DraftReply.model_validate(structured["reply"])
                    violations = check(final, decision, ticket.language)
                    trace.append(
                        {
                            "step": "baseline_model_decision",
                            "violations": [v.model_dump() for v in violations],
                        }
                    )
                else:
                    extraction = Extraction.model_validate(structured)
                    if extraction.language != ticket.language:
                        raise WorkflowStop("trusted_language_changed")
                    order = seen.get(extraction.order_id or "") if not ambiguous else None
                    decision = evaluate(extraction, order, ticket.customer_id, today)
                    trace.append({"step": "decide", "decision": decision.model_dump(mode="json")})
                    rejected: dict[str, Any] | None = None
                    for attempt in range(2):
                        repair_attempted = attempt == 1
                        payload: dict[str, Any] = {
                            "ticket": ticket.model_dump(mode="json"),
                            "decision": decision.model_dump(mode="json"),
                        }
                        if attempt:
                            payload.update(
                                rejected_draft=rejected,
                                violations=[v.model_dump() for v in violations],
                            )
                        draft_raw = await self._generate(
                            ctx,
                            "repair" if attempt else "draft",
                            [{"role": "user", "content": canonical(payload)}],
                            prompts.REPAIR if attempt else prompts.DRAFT,
                            prompts.DRAFT_FORMAT,
                            False,
                        )
                        rejected = draft_raw
                        try:
                            rejected = self._structured(draft_raw)
                            draft = DraftReply.model_validate(rejected)
                            violations = check(draft, decision, ticket.language)
                        except (ValidationError, ValueError, TypeError):
                            draft = None
                            violations = [
                                Violation(code="schema", detail="Invalid structured draft")
                            ]
                        trace.append(
                            {
                                "step": "repair" if attempt else "draft",
                                "violations": [v.model_dump() for v in violations],
                            }
                        )
                        if not violations:
                            final = draft
                            break
                    if final is None:
                        raise WorkflowStop("reply_validation_failed")
            ctx.guard()
            if create_actions and order and not baseline:
                pending = store.create_pending(
                    ticket_id, order, decision, ticket.customer_id, today
                )
        except WorkflowStop as exc:
            status, error_code = exc.status, exc.code
        except (ValidationError, ValueError, KeyError, TypeError):
            status, error_code = "failed", "invalid_provider_contract"
        if status != "completed" or final is None:
            decision = Decision(
                outcome="needs_human",
                actions=[],
                clause_ids=decision.clause_ids,
                reasons=[error_code or "workflow_failed"],
            )
            final = render(decision, ticket.language)
            if check(final, decision, ticket.language):
                raise ValueError("Internal handoff template failed validation")
            pending = []
            trace.append({"step": "handoff", "reason": error_code})
        elapsed = (perf_counter() - ctx.started) * 1000
        api_ms = sum(call["api_round_trip_ms"] for call in ctx.calls)
        generation_ms = sum(
            call["api_round_trip_ms"] for call in ctx.calls if call["kind"] == "generation"
        )
        count_ms = api_ms - generation_ms
        result = {
            "run_id": ctx.run_id,
            "ticket_id": ticket_id,
            "status": status,
            "provenance": self.provenance,
            "system": "baseline" if baseline else "policydesk",
            "model": self.model,
            "decision": decision.model_dump(mode="json"),
            "reply": final.model_dump(mode="json"),
            "extraction": extraction.model_dump(mode="json") if extraction else None,
            "violations": [v.model_dump() for v in violations],
            "pending_actions": pending,
            "trace": trace,
            "repair_attempted": repair_attempted,
            "error_code": error_code,
            "calls": ctx.calls,
            "metrics": {
                "estimated_cost_usd": None if ctx.unknown else str(ctx.spent),
                "known_cost_usd": str(ctx.spent),
                "unknown_cost": ctx.unknown,
                "api_round_trip_ms": api_ms,
                "generation_round_trip_ms": generation_ms,
                "token_count_round_trip_ms": count_ms,
                "workflow_ms": elapsed,
                "local_processing_ms": max(0, elapsed - api_ms),
                "ttft_ms": None,
                "measured_at": ctx.measured_at,
                "finished_at": timestamp(),
            },
        }
        result = _scrub(result, self._key)
        store.audit(ticket_id, "live_result", result)
        if record_dir is not None:
            record_dir.mkdir(parents=True, exist_ok=True)
            envelope = _scrub(
                {
                    "schema_version": 2,
                    "kind": "openai_responses_recording",
                    "provenance": self.provenance,
                    "metadata": self.benchmark_metadata(),
                    "measured_at": ctx.measured_at,
                    "recorded_at": timestamp(),
                    "exchanges": ctx.captures,
                    "result": result,
                },
                self._key,
            )
            envelope["integrity"] = digest(envelope)
            target = record_dir / f"{ctx.run_id}.json"
            target.write_text(canonical(envelope) + "\n", encoding="utf-8")
        return result


def replay_recording(path: Path) -> dict[str, Any]:
    """Read an integrity-checked opt-in recording, preserving original measurements."""
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(envelope, dict):
        raise ValueError("Invalid recording")
    integrity = envelope.pop("integrity", None)
    if (
        integrity != digest(envelope)
        or envelope.get("schema_version") != 2
        or envelope.get("kind") != "openai_responses_recording"
    ):
        raise ValueError("Invalid recording integrity or version")
    if envelope.get("provenance") not in ("mock_openai_transport", "openai_live"):
        raise ValueError("Invalid recording provenance")
    result = envelope["result"]
    if (
        result.get("provenance") != envelope["provenance"]
        or result["metrics"]["measured_at"] != envelope["measured_at"]
    ):
        raise ValueError("Recording provenance or timestamp mismatch")
    Decision.model_validate(result["decision"])
    DraftReply.model_validate(result["reply"])
    if result.get("extraction") is not None:
        Extraction.model_validate(result["extraction"])
    if _scrub(envelope) != envelope:
        raise ValueError("Unsafe credential material in recording")
    return {**result, "replayed": True, "recording_provenance": envelope["provenance"]}

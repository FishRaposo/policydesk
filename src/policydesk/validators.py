"""Eight bounded deterministic checks; phrase rules do not prove semantic safety."""

import re
from decimal import Decimal
from functools import lru_cache

import yaml
from lingua import Language as LinguaLanguage
from lingua import LanguageDetectorBuilder

from .models import Decision, DraftReply, Language, Violation
from .replies import next_step
from .resources import DATA

NUMBER = r"\d(?:[\d.,\u00a0 ]*\d)?"
MONEY_RE = re.compile(
    rf"(?P<prefix>R\$|MX\$|US\$|BRL\b|MXN\b|USD\b|\$)\s*(?P<value>{NUMBER})(?:\s*(?P<suffix>BRL|MXN|USD)\b)?",
    re.IGNORECASE,
)
BARE_MONEY_RE = re.compile(
    rf"(?<![\w.,])(?P<value>{NUMBER})\s*(?P<suffix>BRL|MXN|USD)\b", re.IGNORECASE
)


def parse_number(value: str) -> Decimal:
    value = value.replace(" ", "").replace("\u00a0", "")
    if "," in value and "." in value:
        decimal_mark = "," if value.rfind(",") > value.rfind(".") else "."
        value = value.replace("." if decimal_mark == "," else ",", "").replace(decimal_mark, ".")
    elif "," in value or "." in value:
        mark = "," if "," in value else "."
        parts = value.split(mark)
        if len(parts[-1]) == 3:
            value = "".join(parts)
        elif len(parts) == 2 and len(parts[-1]) in (1, 2):
            value = value.replace(mark, ".")
        else:
            raise ValueError("Ambiguous money punctuation")
    return Decimal(value)


def body_money(body: str, order_currency: str | None) -> list[tuple[Decimal, str]]:
    parsed: list[tuple[Decimal, str]] = []
    spans: list[tuple[int, int]] = []
    for match in MONEY_RE.finditer(body):
        prefix = match["prefix"].upper()
        code = {
            "R$": "BRL",
            "MX$": "MXN",
            "US$": "USD",
            "BRL": "BRL",
            "MXN": "MXN",
            "USD": "USD",
        }.get(prefix)
        suffix = (match["suffix"] or "").upper()
        if prefix == "$":
            code = suffix or ("USD" if order_currency == "USD" else "AMBIGUOUS")
        elif suffix and code != suffix:
            code = "CONFLICT"
        parsed.append((parse_number(match["value"]), code or "AMBIGUOUS"))
        spans.append(match.span())
    for match in BARE_MONEY_RE.finditer(body):
        if not any(left <= match.start() < right for left, right in spans):
            parsed.append((parse_number(match["value"]), match["suffix"].upper()))
    return parsed


@lru_cache(maxsize=1)
def detector():
    return LanguageDetectorBuilder.from_languages(
        LinguaLanguage.PORTUGUESE, LinguaLanguage.SPANISH, LinguaLanguage.ENGLISH
    ).build()


@lru_cache(maxsize=1)
def phrases() -> dict[str, list[str]]:
    return yaml.safe_load((DATA / "phrases.yaml").read_text(encoding="utf-8"))


def check(
    draft: DraftReply,
    decision: Decision,
    language: Language,
    forbidden_values: tuple[str, ...] = (),
) -> list[Violation]:
    violations: list[Violation] = []

    def fail(code: str, detail: str) -> None:
        violations.append(Violation(code=code, detail=detail))

    if sorted(draft.cited_clause_ids) != sorted(decision.clause_ids):
        fail("clauses_subset", "Citations must match the decision clauses, without omissions")
    refund = decision.refund
    amount = refund.amount if refund else None
    currency = refund.currency if refund else None
    if draft.stated_amount != amount or draft.stated_currency != currency:
        fail("amount_matches", "Structured money differs from the decision")
    try:
        amounts = body_money(draft.body, currency)
        if any(value != amount or code != currency for value, code in amounts):
            fail("body_money_matches", "Body money differs from the decision")
        elif amount is not None and not amounts:
            fail("body_money_matches", "Refund reply must state its amount and currency")
        # Bare decimal amounts are not allowed to evade currency parsing.
        masked = MONEY_RE.sub("", BARE_MONEY_RE.sub("", draft.body))
        if re.search(r"\d+[.,]\d{1,2}\b", masked):
            fail("body_money_matches", "Unqualified decimal amount in reply")
    except (ValueError, ArithmeticError):
        fail("body_money_matches", "Unparseable money in reply")
    if draft.next_step != next_step(decision):
        fail("next_step_consistent", "Reply next step differs from the decision")
    lower = draft.body.casefold().replace("’", "'")
    if decision.outcome != "approve" and any(p in lower for p in phrases()["promises"]):
        fail("no_unapproved_promise", "Unapproved promise phrase")
    if any(p in lower for p in phrases()["completed"]):
        fail("no_completed_claim", "Execution is never performed by this prototype")
    if "ID-1" in decision.clause_ids and (
        re.search(r"\bGN-\d+\b", draft.body, re.IGNORECASE)
        or any(v and v.casefold() in lower for v in forbidden_values)
    ):
        fail("no_foreign_order_data", "Foreign-order sentinel or identifier in reply")
    detected = detector().detect_language_of(draft.body)
    expected = {
        "pt": LinguaLanguage.PORTUGUESE,
        "es": LinguaLanguage.SPANISH,
        "en": LinguaLanguage.ENGLISH,
    }[language]
    if detected != expected:
        fail("language_matches", "Reply language does not match the trusted ticket language")
    return violations

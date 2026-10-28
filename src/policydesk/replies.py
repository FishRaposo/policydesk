"""Deterministic localized fixture/template replies, never model output."""

from .models import Decision, DraftReply, Language

TEXT = {
    "en": {
        "approve": "Your request meets the fictional policy. The proposed action is pending human confirmation; nothing has been executed.",
        "deny": "Your request falls outside the fictional policy window. No refund has been approved. You can ask a support person to review the request.",
        "needs_human": "A support person needs to review your request before any action can be authorized. We cannot confirm a refund or share additional order information.",
        "information": "This is the carrier status supplied by the fictional order record. No financial action is proposed. Please contact support if you need further assistance.",
        "refund": "Proposed refund, pending human confirmation: {currency} {amount}.",
        "cancel": "Subscription cancellation is proposed for the next cycle and is pending human confirmation.",
    },
    "pt": {
        "approve": "Sua solicitação atende à política fictícia. A ação proposta aguarda confirmação humana; nenhuma ação foi executada.",
        "deny": "Sua solicitação está fora do prazo da política fictícia. Nenhum reembolso foi autorizado. Você pode pedir a uma pessoa do suporte que revise a solicitação.",
        "needs_human": "Uma pessoa do suporte precisa avaliar sua solicitação antes de autorizar qualquer ação. Não podemos confirmar um reembolso nem compartilhar informações adicionais do pedido.",
        "information": "Este é o status da transportadora informado no registro fictício do pedido. Nenhuma ação financeira foi proposta. Entre em contato com o suporte se precisar de mais ajuda.",
        "refund": "Reembolso proposto, aguardando confirmação humana: {currency} {amount}.",
        "cancel": "O cancelamento da assinatura foi proposto para o próximo ciclo e aguarda confirmação humana.",
    },
    "es": {
        "approve": "Su solicitud cumple la política ficticia. La acción propuesta está pendiente de confirmación humana; no se ha ejecutado ninguna acción.",
        "deny": "Su solicitud está fuera del plazo de la política ficticia. No se ha autorizado ningún reembolso. Puede pedir a una persona de soporte que revise la solicitud.",
        "needs_human": "Una persona de soporte debe revisar su solicitud antes de autorizar cualquier acción. No podemos confirmar un reembolso ni compartir información adicional del pedido.",
        "information": "Este es el estado del transportista indicado en el registro ficticio del pedido. No se propone ninguna acción financiera. Contacte con soporte si necesita más ayuda.",
        "refund": "Reembolso propuesto, pendiente de confirmación humana: {currency} {amount}.",
        "cancel": "Se propone cancelar la suscripción en el próximo ciclo, pendiente de confirmación humana.",
    },
}


def next_step(decision: Decision) -> str:
    if decision.outcome != "approve":
        return {"deny": "denied", "needs_human": "handed_off", "information": "information"}[
            decision.outcome
        ]
    return "refund_pending_confirmation" if decision.refund else "cancellation_pending_confirmation"


def render(decision: Decision, language: Language) -> DraftReply:
    text = TEXT[language]
    body = text[decision.outcome]
    if decision.refund:
        body += " " + text["refund"].format(
            currency=decision.refund.currency, amount=f"{decision.refund.amount:.2f}"
        )
    if any(a.kind == "cancel_subscription" for a in decision.actions):
        body += " " + text["cancel"]
    return DraftReply.model_validate(
        {
            "body": body,
            "cited_clause_ids": decision.clause_ids,
            "stated_amount": decision.refund.amount if decision.refund else None,
            "stated_currency": decision.refund.currency if decision.refund else None,
            "next_step": next_step(decision),
        }
    )

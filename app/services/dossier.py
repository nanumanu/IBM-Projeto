"""Agentes Investigador e Decisão: reúnem o contexto e montam o dossiê com recomendação.

A recomendação vira ações com status 'proposed'. Nada é executado aqui.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Action, Case, Dispute, Transaction, utcnow
from app.services import watsonx
from app.services.graph import build_network
from app.fmt import brl

SIGNAL_LABELS = {
    "network_fan_in": "Padrão de rede (muitas instituições de origem)",
    "pass_through": "Repasse rápido do dinheiro",
    "new_account": "Conta recente",
    "disputes": "Contestações",
    "inbound_spike": "Entrada fora do padrão",
}


def investigate(db: Session, case: Case) -> dict:
    acc: Account = case.account
    network = build_network(db, acc.id, hours=24, depth=2)
    disputes = db.execute(
        select(Dispute, Transaction)
        .join(Transaction, Transaction.id == Dispute.transaction_id)
        .where(Transaction.dest_account_id == acc.id)
        .order_by(Dispute.created_at.desc())
    ).all()
    recent = db.scalars(
        select(Transaction)
        .where((Transaction.dest_account_id == acc.id) | (Transaction.source_account_id == acc.id))
        .order_by(Transaction.created_at.desc())
        .limit(30)
    ).all()
    return {
        "case_id": case.id,
        "account": {
            "account_id": acc.id,
            "institution_code": acc.institution_code,
            "institution_name": acc.institution.name,
            "holder_name": acc.holder_name,
            "holder_type": acc.holder_type,
            "document_masked": acc.document_masked,
            "age_days": (utcnow() - acc.opened_at).days,
            "status": acc.status,
        },
        "signals": case.signals,
        "network": network,
        "disputes": [
            {
                "dispute_id": d.id,
                "transaction_id": t.id,
                "source_account_id": t.source_account_id,
                "amount": t.amount,
                "reason": d.reason,
                "created_at": d.created_at,
            }
            for d, t in disputes
        ],
        "recent_transactions": [
            {
                "transaction_id": t.id,
                "direction": "in" if t.dest_account_id == acc.id else "out",
                "counterparty": t.source_account_id if t.dest_account_id == acc.id else t.dest_account_id,
                "amount": t.amount,
                "channel": t.channel,
                "status": t.status,
                "created_at": t.created_at,
            }
            for t in recent
        ],
    }


def _recommend(case: Case, inv: dict) -> tuple[str, str, list[dict]]:
    sig = case.signals
    summary = inv["network"]["summary"]
    remaining = summary["estimated_remaining"]
    pass_through = sig.get("pass_through", {}).get("value", 0)
    downstream = inv["network"]["downstream"]

    actions: list[dict] = []
    if case.risk_score >= 85:
        rec = "block_and_recover"
        actions.append({"type": "block_account", "detail": {"account_id": case.account_id}})
        for d in downstream:
            if d["age_days"] < 30:
                actions.append({
                    "type": "block_account",
                    "detail": {"account_id": d["account_id"], "reason": "destino do repasse, conta recente"},
                })
        for disp in inv["disputes"]:
            actions.append({
                "type": "request_return",
                "detail": {"transaction_id": disp["transaction_id"], "amount": disp["amount"]},
            })
        why = (
            "Score muito alto com padrão típico de conta de passagem. Bloquear a conta e os "
            "destinos recentes do repasse interrompe a dispersão; pedir devolução das "
            "transferências contestadas protege as vítimas já identificadas."
        )
    elif case.risk_score >= 60:
        rec = "hold_and_review"
        actions.append({"type": "block_account", "detail": {"account_id": case.account_id}})
        why = (
            "Score acima do limiar, mas sem a combinação completa de sinais de conta-laranja. "
            "Bloqueio cautelar enquanto o analista confirma com a instituição de origem."
        )
    else:
        rec = "monitor"
        why = "Sinais fracos. Manter em observação, sem ação sobre a conta."

    if pass_through >= 0.8 and remaining > 0:
        why += f" Ainda há cerca de {brl(remaining)} na conta que podem ser preservados."
    return rec, why, actions


def build_dossier(db: Session, case: Case) -> dict:
    inv = investigate(db, case)
    rec, why, proposed = _recommend(case, inv)

    ranked = sorted(case.signals.items(), key=lambda kv: -kv[1]["value"])
    evidence = [
        {"signal": name, "label": SIGNAL_LABELS.get(name, name), "strength": s["value"], "evidence": s["evidence"]}
        for name, s in ranked
        if s["value"] > 0
    ]
    summary = inv["network"]["summary"]
    acc = inv["account"]

    facts = "\n".join(
        [
            f"Conta {acc['account_id']} ({acc['institution_name']}), aberta há {acc['age_days']} dias.",
            f"Score de risco: {case.risk_score}/100.",
            *[f"- {e['label']}: {e['evidence']}" for e in evidence],
            f"Rede em 24h: {summary['accounts_in_network']} contas em "
            f"{summary['institutions_in_network']} instituições.",
            f"Entrou {brl(summary['inbound_total'])}, saiu {brl(summary['outbound_total'])}.",
        ]
    )
    template = (
        f"A conta {acc['account_id']} tem score {case.risk_score}/100. "
        + " ".join(e["evidence"] for e in evidence[:3])
        + " Esse desenho só é visível somando o que várias instituições veem separadamente."
    )
    narrative = watsonx.generate_narrative(facts)

    # substitui ações propostas anteriores (dossiê pode ser regenerado antes da decisão)
    for a in list(case.actions):
        if a.status == "proposed":
            case.actions.remove(a)
    for p in proposed:
        case.actions.append(Action(type=p["type"], detail=p["detail"]))

    dossier = {
        "case_id": case.id,
        "generated_at": utcnow().isoformat(),
        "risk_score": case.risk_score,
        "recommendation": rec,
        "justification": why,
        "narrative": narrative or template,
        "narrative_source": "watsonx.ai" if narrative else "template",
        "evidence": evidence,
        "account": acc,
        "network_summary": summary,
        "money_trail": inv["network"]["downstream"],
        "disputes": inv["disputes"],
        "checklist": [
            "Confirmar com ao menos uma instituição de origem se houve relato de golpe.",
            "Verificar se a conta tem justificativa comercial para receber de muitas origens.",
            "Conferir se os destinos do repasse também são contas recentes.",
        ],
    }
    # serializa datas para guardar em JSON
    case.dossier = _jsonable(dossier)
    case.recommendation = rec
    case.status = "awaiting_approval"
    db.flush()
    return case.dossier


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj

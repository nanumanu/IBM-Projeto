"""Agente Comunicação: mensagens claras para vítimas e titulares, sem jargão técnico."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, Dispute, Notification, Transaction
from app.fmt import brl

SAFETY_TIP = (
    "Lembre-se: a sua instituição nunca pede senha, código de verificação ou transferência "
    "para 'conta de segurança'."
)


def notify(db: Session, case: Case) -> list[Notification]:
    if case.status != "approved":
        from app.services.response import DecisionError

        raise DecisionError("Notificações só são enviadas depois que o analista aprova o caso.")

    created: list[Notification] = []
    already = {(n.account_id, n.audience) for n in db.scalars(
        select(Notification).where(Notification.case_id == case.id)
    )}

    # titular da conta investigada (o bloqueio pode não ter sido aprovado)
    if (case.account_id, "holder") not in already:
        blocked = case.account.status == "blocked"
        created.append(Notification(
            case_id=case.id,
            account_id=case.account_id,
            audience="holder",
            message=(
                ("Sua conta foi bloqueada temporariamente para uma verificação de segurança. "
                 if blocked else
                 "Movimentações recentes da sua conta estão em verificação de segurança. ")
                + "Se você reconhece essas movimentações, procure sua agência ou o canal "
                "oficial do seu banco com um documento de identificação."
            ),
        ))

    # vítimas: quem contestou transferências para a conta
    disputed = db.execute(
        select(Transaction)
        .join(Dispute, Dispute.transaction_id == Transaction.id)
        .where(Transaction.dest_account_id == case.account_id)
    ).scalars().all()
    for tx in disputed:
        if (tx.source_account_id, "victim") in already:
            continue
        already.add((tx.source_account_id, "victim"))
        returned = tx.status == "returned"
        created.append(Notification(
            case_id=case.id,
            account_id=tx.source_account_id,
            audience="victim",
            message=(
                f"Recebemos sua contestação da transferência de {brl(tx.amount)}. "
                + ("A devolução foi solicitada e você será avisado assim que o valor voltar. "
                   if returned else
                   "O caso está em análise e você será avisado sobre a devolução. ")
                + SAFETY_TIP
            ),
        ))

    db.add_all(created)
    db.flush()
    return created

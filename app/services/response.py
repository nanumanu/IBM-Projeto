"""Agente Resposta: executa ações SOMENTE depois da aprovação de um analista."""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Account, Case, Transaction, utcnow


class DecisionError(HTTPException):
    def __init__(self, msg: str):
        super().__init__(status.HTTP_409_CONFLICT, msg)


def _execute(db: Session, action) -> None:
    if action.type == "block_account":
        acc = db.get(Account, action.detail["account_id"])
        if acc:
            acc.status = "blocked"
    elif action.type == "request_return":
        tx = db.get(Transaction, action.detail["transaction_id"])
        if tx and tx.status == "completed":
            tx.status = "returned"
    action.status = "executed"
    action.executed_at = utcnow()


def decide(
    db: Session, case: Case, approve: bool, analyst: str, note: str | None, action_ids: list[str] | None
) -> Case:
    if case.status != "awaiting_approval":
        raise DecisionError(
            f"Caso está '{case.status}'. Só é possível decidir casos com dossiê gerado "
            "(status 'awaiting_approval')."
        )
    proposed = [a for a in case.actions if a.status == "proposed"]
    if action_ids is not None:
        unknown = set(action_ids) - {a.id for a in proposed}
        if unknown:
            raise DecisionError(f"Ações inexistentes ou já decididas: {sorted(unknown)}")

    for a in proposed:
        if approve and (action_ids is None or a.id in action_ids):
            _execute(db, a)
        else:
            a.status = "discarded"

    case.status = "approved" if approve else "rejected"
    case.decided_by = analyst
    case.decision_note = note
    case.decided_at = utcnow()
    db.flush()
    return case

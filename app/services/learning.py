"""Agente Aprendizado: cada decisão do analista ajusta os pesos dos sinais."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Action, Case, Feedback, SignalWeight, Transaction, utcnow
from app.services.scoring import WEIGHT_MAX, WEIGHT_MIN, ensure_weights

STEP = 0.10      # ajuste de 10% por feedback
ACTIVE = 0.5     # só ajusta sinais que de fato pesaram no caso


def apply_feedback(db: Session, case: Case, label: str, analyst: str, comment: str | None) -> dict:
    from app.services.response import DecisionError

    if case.status not in ("approved", "rejected"):
        raise DecisionError("Feedback só depois da decisão do analista.")
    if db.scalar(select(Feedback).where(Feedback.case_id == case.id)):
        raise DecisionError("Este caso já recebeu feedback.")

    ensure_weights(db)
    factor = 1 + STEP if label == "fraud" else 1 - STEP
    changes = {}
    for name, sig in case.signals.items():
        if sig["value"] < ACTIVE:
            continue
        w = db.get(SignalWeight, name)
        old = w.weight
        w.weight = round(max(WEIGHT_MIN, min(WEIGHT_MAX, old * factor)), 2)
        w.updates += 1
        w.updated_at = utcnow()
        changes[name] = {"before": old, "after": w.weight}

    db.add(Feedback(case_id=case.id, label=label, analyst=analyst, comment=comment))
    case.status = "closed"
    db.flush()
    return changes


def metrics(db: Session) -> dict:
    by_status = dict(db.execute(select(Case.status, func.count()).group_by(Case.status)).all())
    labels = dict(db.execute(select(Feedback.label, func.count()).group_by(Feedback.label)).all())
    labelled = sum(labels.values())

    decided = db.scalars(select(Case).where(Case.decided_at.is_not(None))).all()
    minutes = [(c.decided_at - c.created_at).total_seconds() / 60 for c in decided]

    returned = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(Transaction.status == "returned")
    )
    held = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(Transaction.status == "held")
    )
    executed = db.scalar(select(func.count(Action.id)).where(Action.status == "executed"))
    return {
        "cases_by_status": by_status,
        "feedback": labels,
        "precision": round(labels.get("fraud", 0) / labelled, 3) if labelled else None,
        "avg_minutes_to_decision": round(sum(minutes) / len(minutes), 1) if minutes else None,
        "executed_actions": executed,
        "amount_returned": round(returned, 2),
        "amount_held": round(held, 2),
    }

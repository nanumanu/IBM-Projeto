"""Agente Sentinela: transforma o movimento de uma conta em sinais explicáveis e num score.

Cada sinal vale de 0 a 1 e vem acompanhado da evidência que o gerou. O score (0-100) é a
média ponderada dos sinais; os pesos ficam no banco e são ajustados pelo Aprendizado.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Account, Case, Dispute, Feedback, SignalWeight, Transaction, utcnow
from app.fmt import brl

DEFAULT_WEIGHTS: dict[str, float] = {
    "network_fan_in": 35.0,   # recebe de muitas instituições em pouco tempo (só visível na rede)
    "pass_through": 25.0,     # repassa quase tudo o que recebe (comportamento de conta-laranja)
    "new_account": 15.0,      # conta aberta há pouco tempo
    "disputes": 15.0,         # transferências recebidas que foram contestadas
    "inbound_spike": 10.0,    # entrada muito acima do histórico da própria conta
}
WEIGHT_MIN, WEIGHT_MAX = 5.0, 60.0
ACTIVE_CASE_STATUSES = ("open", "awaiting_approval")


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class Signal:
    name: str
    value: float
    evidence: str
    data: dict = field(default_factory=dict)


@dataclass
class RiskAssessment:
    account_id: str
    score: float
    signals: list[Signal]
    window_start: datetime
    window_end: datetime

    def signals_dict(self) -> dict:
        return {
            s.name: {"value": round(s.value, 3), "evidence": s.evidence, **s.data}
            for s in self.signals
        }


def ensure_weights(db: Session) -> dict[str, float]:
    rows = {w.signal: w for w in db.scalars(select(SignalWeight))}
    for name, weight in DEFAULT_WEIGHTS.items():
        if name not in rows:
            db.add(SignalWeight(signal=name, weight=weight))
    db.flush()
    return {w.signal: w.weight for w in db.scalars(select(SignalWeight))}


def assess_account(db: Session, account: Account, at: datetime | None = None) -> RiskAssessment:
    settings = get_settings()
    at = at or utcnow()
    start = at - timedelta(hours=settings.window_hours)

    inbound = db.execute(
        select(Transaction, Account.institution_code)
        .join(Account, Account.id == Transaction.source_account_id)
        .where(
            Transaction.dest_account_id == account.id,
            Transaction.created_at > start,
            Transaction.created_at <= at,
        )
    ).all()
    inflow = sum(t.amount for t, _ in inbound)
    institutions = sorted({inst for _, inst in inbound})

    outflow = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
            Transaction.source_account_id == account.id,
            Transaction.created_at > start,
            Transaction.created_at <= at,
        )
    ) or 0.0

    history_start = at - timedelta(days=30)
    history_inflow = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
            Transaction.dest_account_id == account.id,
            Transaction.created_at > history_start,
            Transaction.created_at <= start,
        )
    ) or 0.0
    age_days = max(0, (at - account.opened_at).days)
    history_days = max(1, min(30, age_days))
    # entrada típica numa janela do mesmo tamanho, com piso para contas sem histórico
    windows_per_day = 24 / settings.window_hours
    baseline = max(history_inflow / history_days / windows_per_day, 300.0)

    dispute_count = db.scalar(
        select(func.count(Dispute.id))
        .join(Transaction, Transaction.id == Dispute.transaction_id)
        .where(
            Transaction.dest_account_id == account.id,
            Dispute.created_at > at - timedelta(days=7),
            Dispute.created_at <= at,
        )
    ) or 0

    n_inst = len(institutions)
    pass_ratio = (outflow / inflow) if inflow > 0 else 0.0
    spike_ratio = inflow / baseline

    signals = [
        Signal(
            "network_fan_in",
            _clamp((n_inst - 3) / 7),
            f"Recebeu de {n_inst} instituições diferentes nas últimas "
            f"{settings.window_hours}h ({len(inbound)} transferências).",
            {"institutions": n_inst, "inbound_count": len(inbound)},
        ),
        Signal(
            "pass_through",
            _clamp((pass_ratio - 0.5) / 0.4) if inflow > 0 else 0.0,
            f"Repassou {pass_ratio:.0%} do que recebeu na janela "
            f"(entrou {brl(inflow)}, saiu {brl(outflow)}).",
            {"ratio": round(pass_ratio, 3), "inflow": round(inflow, 2), "outflow": round(outflow, 2)},
        ),
        Signal(
            "new_account",
            1.0 if age_days < 30 else 0.5 if age_days < 90 else 0.0,
            f"Conta aberta há {age_days} dias.",
            {"age_days": age_days},
        ),
        Signal(
            "disputes",
            _clamp(dispute_count / 3),
            f"{dispute_count} transferência(s) recebida(s) contestada(s) nos últimos 7 dias.",
            {"count": dispute_count},
        ),
        Signal(
            "inbound_spike",
            _clamp((spike_ratio - 3) / 7),
            f"Entrada {spike_ratio:.1f}x acima do normal da conta para o mesmo intervalo.",
            {"ratio": round(spike_ratio, 2)},
        ),
    ]

    weights = ensure_weights(db)
    total_weight = sum(weights[s.name] for s in signals)
    score = 100 * sum(weights[s.name] * s.value for s in signals) / total_weight
    return RiskAssessment(account.id, round(score, 1), signals, start, at)


def active_case_for(db: Session, account_id: str) -> Case | None:
    return db.scalar(
        select(Case).where(Case.account_id == account_id, Case.status.in_(ACTIVE_CASE_STATUSES))
    )


def open_case_if_needed(db: Session, assessment: RiskAssessment) -> tuple[Case | None, bool]:
    """Abre caso se o score passou do limiar. Retorna (caso, criado_agora)."""
    if assessment.score < get_settings().case_threshold:
        return active_case_for(db, assessment.account_id), False

    case = active_case_for(db, assessment.account_id)
    if case:
        if assessment.score > case.risk_score and case.status == "open":
            case.risk_score = assessment.score
            case.signals = assessment.signals_dict()
        return case, False

    # analista já confirmou que era legítimo: só reabre se o risco piorou desde então
    last = db.scalar(
        select(Case).where(Case.account_id == assessment.account_id, Case.status == "closed")
        .order_by(Case.updated_at.desc()).limit(1)
    )
    if last is not None:
        label = db.scalar(select(Feedback.label).where(Feedback.case_id == last.id))
        if label == "legit" and assessment.score <= last.risk_score:
            return None, False

    case = Case(
        account_id=assessment.account_id,
        risk_score=assessment.score,
        signals=assessment.signals_dict(),
    )
    db.add(case)
    db.flush()
    return case, True


def scan(db: Session, at: datetime | None = None) -> list[tuple[RiskAssessment, Case | None, bool]]:
    """Avalia toda conta que recebeu dinheiro na janela recente."""
    at = at or utcnow()
    start = at - timedelta(hours=get_settings().window_hours)
    account_ids = db.scalars(
        select(Transaction.dest_account_id)
        .where(Transaction.created_at > start, Transaction.created_at <= at)
        .distinct()
    ).all()
    results = []
    for acc in db.scalars(select(Account).where(Account.id.in_(account_ids))):
        if acc.status == "blocked":
            continue
        assessment = assess_account(db, acc, at)
        case, created = open_case_if_needed(db, assessment)
        results.append((assessment, case, created))
    return results

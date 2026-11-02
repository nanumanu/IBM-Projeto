"""Sentinela: ingestão, contestações, contas e score."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Account, Dispute, Transaction
from app.schemas import (
    AccountOut, DisputeIn, DisputeOut, IngestResult, RiskOut, ScanItem, ScanOut, SignalOut,
    TransactionIn, TransactionOut,
)
from app.security import require_agent
from app.services import scoring

router = APIRouter(tags=["Sentinela"], dependencies=[Depends(require_agent)])


def _account_or_404(db: Session, account_id: str) -> Account:
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(404, f"Conta {account_id} não encontrada.")
    return acc


@router.post("/transactions", response_model=IngestResult, operation_id="ingest_transaction",
             summary="Registrar uma transferência e avaliar o destino")
def ingest_transaction(body: TransactionIn, db: Session = Depends(get_db)):
    """Registra uma transferência entre contas e recalcula o risco da conta de destino.
    Se o score passar do limiar, abre um caso automaticamente. Transferências que envolvem
    conta bloqueada ficam retidas (status 'held')."""
    if body.source_account_id == body.dest_account_id:
        raise HTTPException(422, "Origem e destino não podem ser a mesma conta.")
    src = _account_or_404(db, body.source_account_id)
    dst = _account_or_404(db, body.dest_account_id)

    held = "blocked" in (src.status, dst.status)
    tx = Transaction(**body.model_dump(), status="held" if held else "completed")
    db.add(tx)
    db.flush()

    assessment = scoring.assess_account(db, dst, tx.created_at)
    tx.risk_score = assessment.score
    case, created = (None, False) if held else scoring.open_case_if_needed(db, assessment)
    db.commit()

    if held:
        msg = "Transferência retida: envolve conta bloqueada por decisão de analista."
    elif created:
        msg = f"Score {assessment.score} acima do limiar. Caso {case.id} aberto."
    else:
        msg = f"Transferência registrada. Score do destino: {assessment.score}."
    return IngestResult(
        transaction=TransactionOut.model_validate(tx), dest_risk_score=assessment.score,
        held=held, case_id=case.id if case else None, case_opened=created, message=msg,
    )


@router.get("/transactions", response_model=list[TransactionOut], operation_id="list_transactions",
            summary="Listar transferências de uma conta")
def list_transactions(
    account_id: str = Query(description="Conta (entradas e saídas)"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Histórico de transferências de uma conta, mais recentes primeiro."""
    return db.scalars(
        select(Transaction)
        .where((Transaction.source_account_id == account_id) | (Transaction.dest_account_id == account_id))
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    ).all()


@router.post("/disputes", response_model=DisputeOut, status_code=201, operation_id="open_dispute",
             summary="Registrar contestação de uma transferência")
def open_dispute(body: DisputeIn, db: Session = Depends(get_db)):
    """Registra que o cliente contestou uma transferência (ex.: golpe). Contestações aumentam o
    risco da conta que recebeu o dinheiro."""
    tx = db.get(Transaction, body.transaction_id)
    if not tx:
        raise HTTPException(404, f"Transferência {body.transaction_id} não encontrada.")
    if db.scalar(select(Dispute.id).where(Dispute.transaction_id == tx.id).limit(1)):
        raise HTTPException(409, f"Transferência {tx.id} já foi contestada.")
    d = Dispute(transaction_id=tx.id, reason=body.reason)
    db.add(d)
    db.flush()
    dst = db.get(Account, tx.dest_account_id)
    if dst.status != "blocked":
        scoring.open_case_if_needed(db, scoring.assess_account(db, dst))
    db.commit()
    return d


@router.get("/accounts/{account_id}", response_model=AccountOut, operation_id="get_account",
            summary="Dados cadastrais de uma conta")
def get_account(account_id: str, db: Session = Depends(get_db)):
    """Instituição, titular (documento mascarado), data de abertura e situação da conta."""
    return _account_or_404(db, account_id)


@router.get("/accounts/{account_id}/risk", response_model=RiskOut, operation_id="score_account",
            summary="Calcular o score de risco de uma conta agora")
def score_account(account_id: str, db: Session = Depends(get_db)):
    """Calcula o score (0-100) e devolve cada sinal com a evidência que o gerou. Não abre caso."""
    acc = _account_or_404(db, account_id)
    a = scoring.assess_account(db, acc)
    weights = scoring.ensure_weights(db)
    db.commit()
    threshold = get_settings().case_threshold
    return RiskOut(
        account_id=acc.id, score=a.score, threshold=threshold, above_threshold=a.score >= threshold,
        signals=[SignalOut(name=s.name, value=round(s.value, 3), weight=weights[s.name], evidence=s.evidence)
                 for s in a.signals],
        window_start=a.window_start, window_end=a.window_end,
    )


@router.post("/monitoring/scan", response_model=ScanOut, operation_id="scan_recent_activity",
             summary="Varrer a atividade recente e abrir casos")
def scan_recent_activity(db: Session = Depends(get_db)):
    """Avalia todas as contas que receberam dinheiro na janela recente e abre caso para as que
    passarem do limiar. É o ponto de partida do agente Sentinela."""
    results = scoring.scan(db)
    db.commit()
    threshold = get_settings().case_threshold
    hits = sorted((r for r in results if r[0].score >= threshold), key=lambda r: -r[0].score)
    return ScanOut(
        accounts_evaluated=len(results),
        cases_opened=sum(1 for r in results if r[2]),
        above_threshold=[
            ScanItem(account_id=a.account_id, score=a.score, case_id=c.id if c else None, case_opened=new)
            for a, c, new in hits
        ],
    )

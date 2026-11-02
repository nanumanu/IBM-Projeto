"""Investigador, Decisão, Resposta, Comunicação e Aprendizado: o ciclo de vida do caso."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Case, Notification, SignalWeight
from app.schemas import (
    CaseDetail, CaseSummary, DecisionIn, FeedbackIn, FeedbackOut, NotificationOut, WeightOut,
)
from app.security import require_agent, require_analyst
from app.services import communication, dossier, learning, response, scoring
from app.services.graph import build_network

router = APIRouter()


def _case_or_404(db: Session, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, f"Caso {case_id} não encontrado.")
    return case


# ----------------------------------------------------------------- Investigador
@router.get("/cases", response_model=list[CaseSummary], operation_id="list_cases",
            tags=["Investigador"], dependencies=[Depends(require_agent)],
            summary="Listar casos")
def list_cases(
    status: str | None = Query(None, description="open | awaiting_approval | approved | rejected | closed"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Casos ordenados por score (maior primeiro)."""
    q = select(Case).order_by(Case.risk_score.desc(), Case.created_at.desc()).limit(limit)
    if status:
        q = q.where(Case.status == status)
    return db.scalars(q).all()


@router.get("/cases/{case_id}", response_model=CaseDetail, operation_id="get_case",
            tags=["Investigador"], dependencies=[Depends(require_agent)],
            summary="Detalhes de um caso")
def get_case(case_id: str, db: Session = Depends(get_db)):
    """Situação, sinais, dossiê (se já gerado) e ações propostas ou executadas."""
    return _case_or_404(db, case_id)


@router.get("/cases/{case_id}/investigation", response_model=dict[str, Any],
            operation_id="investigate_case", tags=["Investigador"],
            dependencies=[Depends(require_agent)], summary="Reunir o contexto de um caso")
def investigate_case(case_id: str, db: Session = Depends(get_db)):
    """Junta cadastro da conta, sinais, grafo de relacionamento em 24h, contestações e
    transferências recentes. Use antes de montar o dossiê."""
    return dossier.investigate(db, _case_or_404(db, case_id))


@router.get("/accounts/{account_id}/network", response_model=dict[str, Any],
            operation_id="get_account_network", tags=["Investigador"],
            dependencies=[Depends(require_agent)], summary="Grafo de relacionamento de uma conta")
def get_account_network(
    account_id: str,
    hours: int = Query(24, ge=1, le=168, description="Janela em horas"),
    depth: int = Query(2, ge=1, le=3, description="Saltos a partir da conta"),
    db: Session = Depends(get_db),
):
    """Contas ligadas por transferências, quantas instituições aparecem e para onde o dinheiro
    seguiu depois de sair da conta ('downstream')."""
    if not db.get(Account, account_id):
        raise HTTPException(404, f"Conta {account_id} não encontrada.")
    return build_network(db, account_id, hours, depth)


# ----------------------------------------------------------------- Decisão
@router.post("/cases/{case_id}/dossier", response_model=dict[str, Any],
             operation_id="build_case_dossier", tags=["Decisão"],
             dependencies=[Depends(require_agent)], summary="Gerar dossiê e recomendação")
def build_case_dossier(case_id: str, db: Session = Depends(get_db)):
    """Monta o dossiê com evidências, rastro do dinheiro, recomendação e justificativa, e
    propõe ações. As ações ficam 'proposed' até um analista decidir."""
    case = _case_or_404(db, case_id)
    if case.status not in ("open", "awaiting_approval"):
        raise HTTPException(409, f"Caso já decidido ({case.status}).")
    result = dossier.build_dossier(db, case)
    db.commit()
    return result


# ----------------------------------------------------------------- Resposta (humano)
@router.post("/cases/{case_id}/decision", response_model=CaseDetail, operation_id="decide_case",
             tags=["Resposta"], dependencies=[Depends(require_analyst)],
             summary="Aprovar ou rejeitar as ações de um caso (somente analista)")
def decide_case(case_id: str, body: DecisionIn, db: Session = Depends(get_db)):
    """Decisão humana. Aprovar executa as ações propostas (todas ou só as indicadas em
    action_ids); rejeitar descarta todas. Exige a chave de analista."""
    case = response.decide(
        db, _case_or_404(db, case_id), body.decision == "approve", body.analyst, body.note, body.action_ids
    )
    db.commit()
    return case


# ----------------------------------------------------------------- Comunicação
@router.post("/cases/{case_id}/notifications", response_model=list[NotificationOut],
             operation_id="notify_parties", tags=["Comunicação"],
             dependencies=[Depends(require_agent)], summary="Avisar titular e vítimas")
def notify_parties(case_id: str, db: Session = Depends(get_db)):
    """Gera as mensagens para o titular da conta e para quem contestou transferências.
    Só funciona depois da aprovação do analista. Não repete avisos já enviados."""
    created = communication.notify(db, _case_or_404(db, case_id))
    db.commit()
    return created


@router.get("/cases/{case_id}/notifications", response_model=list[NotificationOut],
            operation_id="list_notifications", tags=["Comunicação"],
            dependencies=[Depends(require_agent)], summary="Mensagens enviadas num caso")
def list_notifications(case_id: str, db: Session = Depends(get_db)):
    return db.scalars(select(Notification).where(Notification.case_id == case_id)).all()


# ----------------------------------------------------------------- Aprendizado
@router.post("/cases/{case_id}/feedback", response_model=FeedbackOut, operation_id="submit_feedback",
             tags=["Aprendizado"], dependencies=[Depends(require_analyst)],
             summary="Confirmar se era fraude (somente analista)")
def submit_feedback(case_id: str, body: FeedbackIn, db: Session = Depends(get_db)):
    """Registra a confirmação final e ajusta os pesos dos sinais que pesaram no caso:
    sobem se era fraude, descem se era falso positivo. Fecha o caso."""
    changes = learning.apply_feedback(db, _case_or_404(db, case_id), body.label, body.analyst, body.comment)
    db.commit()
    return FeedbackOut(case_id=case_id, label=body.label, weight_changes=changes)


@router.get("/learning/weights", response_model=list[WeightOut], operation_id="get_signal_weights",
            tags=["Aprendizado"], dependencies=[Depends(require_agent)],
            summary="Pesos atuais de cada sinal")
def get_signal_weights(db: Session = Depends(get_db)):
    scoring.ensure_weights(db)
    db.commit()
    return db.scalars(select(SignalWeight).order_by(SignalWeight.weight.desc())).all()


@router.get("/metrics", response_model=dict[str, Any], operation_id="get_metrics",
            tags=["Aprendizado"], dependencies=[Depends(require_agent)],
            summary="Indicadores da operação")
def get_metrics(db: Session = Depends(get_db)):
    """Casos por status, precisão (fraudes confirmadas / casos com feedback), tempo médio até a
    decisão e valores devolvidos ou retidos."""
    return learning.metrics(db)

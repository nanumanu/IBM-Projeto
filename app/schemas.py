from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- transações ----------
class TransactionIn(BaseModel):
    source_account_id: str = Field(description="Conta de origem")
    dest_account_id: str = Field(description="Conta de destino")
    amount: float = Field(gt=0, le=1_000_000, description="Valor em reais")
    channel: Literal["PIX", "TED"] = "PIX"


class TransactionOut(ORM):
    id: str
    source_account_id: str
    dest_account_id: str
    amount: float
    channel: str
    created_at: datetime
    status: str
    risk_score: float | None = None


class IngestResult(BaseModel):
    transaction: TransactionOut
    dest_risk_score: float = Field(description="Score de risco da conta de destino após esta transferência")
    held: bool = Field(description="True se a transferência foi retida por envolver conta bloqueada")
    case_id: str | None = None
    case_opened: bool = False
    message: str


class DisputeIn(BaseModel):
    transaction_id: str
    reason: str = Field(max_length=200, description="Relato do cliente, ex.: 'golpe do falso parente'")


class DisputeOut(ORM):
    id: str
    transaction_id: str
    reason: str
    created_at: datetime


# ---------- contas ----------
class AccountOut(ORM):
    id: str
    institution_code: str
    holder_name: str
    holder_type: str
    document_masked: str
    opened_at: datetime
    status: str


class SignalOut(BaseModel):
    name: str
    value: float = Field(description="Intensidade do sinal, de 0 a 1")
    weight: float
    evidence: str


class RiskOut(BaseModel):
    account_id: str
    score: float = Field(description="0 a 100")
    threshold: float
    above_threshold: bool
    signals: list[SignalOut]
    window_start: datetime
    window_end: datetime


class ScanItem(BaseModel):
    account_id: str
    score: float
    case_id: str | None
    case_opened: bool


class ScanOut(BaseModel):
    accounts_evaluated: int
    cases_opened: int
    above_threshold: list[ScanItem]


# ---------- casos ----------
class ActionOut(ORM):
    id: str
    type: str
    status: str
    detail: dict[str, Any]
    executed_at: datetime | None = None


class CaseSummary(ORM):
    id: str
    account_id: str
    status: str
    risk_score: float
    recommendation: str | None = None
    created_at: datetime
    updated_at: datetime


class CaseDetail(CaseSummary):
    signals: dict[str, Any]
    dossier: dict[str, Any] | None = None
    actions: list[ActionOut] = []
    decided_by: str | None = None
    decision_note: str | None = None
    decided_at: datetime | None = None


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    analyst: str = Field(min_length=2, max_length=80, description="Identificação do analista")
    note: str | None = Field(default=None, max_length=1000)
    action_ids: list[str] | None = Field(
        default=None, description="Aprovar só estas ações. Omitido = todas as ações propostas."
    )


class NotificationOut(ORM):
    id: str
    case_id: str
    account_id: str
    audience: str
    channel: str
    message: str
    created_at: datetime


class FeedbackIn(BaseModel):
    label: Literal["fraud", "legit"] = Field(description="Confirmação final: era fraude ou não")
    analyst: str = Field(min_length=2, max_length=80)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackOut(BaseModel):
    case_id: str
    label: str
    weight_changes: dict[str, dict[str, float]]


class WeightOut(ORM):
    signal: str
    weight: float
    updates: int
    updated_at: datetime

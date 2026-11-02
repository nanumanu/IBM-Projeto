"""Modelo de dados do SafeOne.

Todas as datas são UTC sem fuso (naive), para funcionar igual em SQLite e PostgreSQL.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


class Institution(Base):
    __tablename__ = "institutions"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)  # ex.: "BCO01"
    name: Mapped[str] = mapped_column(String(120))


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    institution_code: Mapped[str] = mapped_column(ForeignKey("institutions.code"), index=True)
    holder_name: Mapped[str] = mapped_column(String(120))
    document_masked: Mapped[str] = mapped_column(String(20))  # CPF/CNPJ mascarado, nunca completo
    holder_type: Mapped[str] = mapped_column(String(2), default="PF")  # PF | PJ
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    # active | blocked
    status: Mapped[str] = mapped_column(String(16), default="active")

    institution: Mapped[Institution] = relationship()


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("TX"))
    source_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    dest_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String(8), default="PIX")  # PIX | TED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    # completed | held | returned
    status: Mapped[str] = mapped_column(String(16), default="completed")
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class Dispute(Base):
    """Contestação aberta por um cliente (ex.: MED do Pix)."""

    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("DSP"))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("CASE"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    # open -> awaiting_approval -> approved | rejected -> closed
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)  # sinais que dispararam o caso
    recommendation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dossier: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    account: Mapped[Account] = relationship()
    actions: Mapped[list["Action"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Action(Base):
    """Ação de resposta. Nasce 'proposed' e só vira 'executed' após aprovação humana."""

    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ACT"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    # block_account | hold_pending_transactions | request_return
    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed|executed|discarded
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    case: Mapped[Case] = relationship(back_populates="actions")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("NTF"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    audience: Mapped[str] = mapped_column(String(16))  # victim | holder | institution
    channel: Mapped[str] = mapped_column(String(16), default="app")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("FBK"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True)
    label: Mapped[str] = mapped_column(String(16))  # fraud | legit
    analyst: Mapped[str] = mapped_column(String(80))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SignalWeight(Base):
    """Peso de cada sinal no score. Ajustado pelo agente de Aprendizado."""

    __tablename__ = "signal_weights"

    signal: Mapped[str] = mapped_column(String(40), primary_key=True)
    weight: Mapped[float] = mapped_column(Float)
    updates: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

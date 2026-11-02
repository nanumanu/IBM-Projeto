import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.models import Institution
from app.routers import admin, cases, monitoring

logging.basicConfig(level=logging.INFO)

DESCRIPTION = """
Serviços que os agentes do SafeOne chamam como ferramentas no watsonx Orchestrate.

Fluxo: **Sentinela** detecta → **Investigador** reúne contexto → **Decisão** monta o dossiê
e propõe ações → um **analista humano** aprova ou rejeita → **Resposta** executa →
**Comunicação** avisa titular e vítimas → **Aprendizado** ajusta os pesos com o feedback.

Nenhuma conta é bloqueada e nenhum valor é devolvido sem aprovação de um analista.
Autenticação: cabeçalho `X-API-Key` (chave de agente ou de analista).
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(engine)
    if settings.seed_on_startup:
        with SessionLocal() as db:
            if db.scalar(select(Institution).limit(1)) is None:
                from app.seed import reset_and_seed

                logging.info("Banco vazio, gerando dados sintéticos: %s", reset_and_seed(db))
    yield


app = FastAPI(
    title="SafeOne API",
    version="1.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(monitoring.router)
app.include_router(cases.router)
app.include_router(admin.router)


@app.get("/health", tags=["Admin"], operation_id="health_check", include_in_schema=False)
def health():
    return {"status": "ok"}

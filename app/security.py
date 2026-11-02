import secrets

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _matches(given: str | None, expected: str) -> bool:
    return given is not None and secrets.compare_digest(given, expected)


def require_agent(
    key: str | None = Security(api_key_header), settings: Settings = Depends(get_settings)
) -> str:
    """Aceita agentes e analistas (analista pode tudo que o agente pode)."""
    if _matches(key, settings.agent_api_key):
        return "agent"
    if _matches(key, settings.analyst_api_key):
        return "analyst"
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de API inválida ou ausente.")


def require_analyst(
    key: str | None = Security(api_key_header), settings: Settings = Depends(get_settings)
) -> str:
    """Somente analistas humanos. Garante que nenhuma ação é executada sem aprovação."""
    if _matches(key, settings.analyst_api_key):
        return "analyst"
    if not _matches(key, settings.agent_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de API inválida ou ausente.")
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, "Somente um analista pode aprovar ou executar ações."
    )

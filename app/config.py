from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SafeOne API"
    database_url: str = "sqlite:///./safeone.db"

    # Chaves de acesso. Agentes (Orchestrate) usam a de agente; só a de analista aprova ações.
    agent_api_key: str = "dev-agent-key"
    analyst_api_key: str = "dev-analyst-key"

    # URL pública do serviço (usada no OpenAPI exportado para o Orchestrate)
    public_url: str = "http://localhost:8080"

    # Detecção
    case_threshold: float = 60.0          # score a partir do qual um caso é aberto
    window_hours: int = 2                 # janela de análise do padrão de rede
    seed_on_startup: bool = True          # popula dados sintéticos se o banco estiver vazio

    # watsonx.ai (opcional): narrativa do dossiê. Sem isso, usa template.
    watsonx_api_key: str | None = None
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    watsonx_project_id: str | None = None
    watsonx_model_id: str = "ibm/granite-3-8b-instruct"


@lru_cache
def get_settings() -> Settings:
    return Settings()

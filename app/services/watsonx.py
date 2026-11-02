"""Cliente mínimo do watsonx.ai para redigir a narrativa do dossiê.

Opcional: sem WATSONX_API_KEY e WATSONX_PROJECT_ID, o dossiê usa o texto de template.
Qualquer falha também cai no template, para a demo nunca quebrar por causa da IA.
"""
import logging
import time

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
_token: dict = {"value": None, "expires": 0.0}


def _iam_token(api_key: str) -> str:
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    resp = httpx.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    _token.update(value=body["access_token"], expires=time.time() + body.get("expires_in", 3600))
    return _token["value"]


def generate_narrative(facts: str) -> str | None:
    s = get_settings()
    if not (s.watsonx_api_key and s.watsonx_project_id):
        return None
    prompt = (
        "Você é um analista antifraude. Com base apenas nos fatos abaixo, escreva um parágrafo "
        "curto, objetivo e em português explicando por que este caso merece atenção e o que o "
        "analista deve verificar antes de decidir. Não invente fatos.\n\n"
        f"Fatos:\n{facts}\n\nParágrafo:"
    )
    try:
        resp = httpx.post(
            f"{s.watsonx_url}/ml/v1/text/generation",
            params={"version": "2024-05-01"},
            headers={"Authorization": f"Bearer {_iam_token(s.watsonx_api_key)}"},
            json={
                "model_id": s.watsonx_model_id,
                "project_id": s.watsonx_project_id,
                "input": prompt,
                "parameters": {"decoding_method": "greedy", "max_new_tokens": 300},
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["results"][0]["generated_text"].strip() or None
    except Exception as exc:  # noqa: BLE001 - qualquer erro cai no template
        log.warning("watsonx.ai indisponível, usando template: %s", exc)
        return None

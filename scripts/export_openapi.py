"""Exporta a especificação OpenAPI no formato que o watsonx Orchestrate importa como ferramentas.

Gera:
  openapi/safeone.yaml            todas as ferramentas
  openapi/<agente>.yaml           só as ferramentas de cada agente (Sentinela, Investigador...)

O FastAPI gera OpenAPI 3.1; aqui convertemos para 3.0.3, que é o formato mais compatível
com importadores de ferramentas. Uso:
  PUBLIC_URL=https://safeone.xxxx.codeengine.appdomain.cloud python scripts/export_openapi.py
"""
import copy
import os
import sys
import unicodedata
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SEED_ON_STARTUP", "false")

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


def to_30(node):
    if isinstance(node, list):
        return [to_30(n) for n in node]
    if not isinstance(node, dict):
        return node
    node = {k: to_30(v) for k, v in node.items()}

    any_of = node.get("anyOf")
    if isinstance(any_of, list) and {"type": "null"} in any_of:
        rest = [s for s in any_of if s != {"type": "null"}]
        node.pop("anyOf")
        if len(rest) == 1:
            node = {**rest[0], **node}
        else:
            node["anyOf"] = rest
        node["nullable"] = True

    for key, base in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        if isinstance(node.get(key), (int, float)) and not isinstance(node.get(key), bool):
            node[base] = node.pop(key)
            node[key] = True
    if node.get("additionalProperties") == {}:
        node["additionalProperties"] = True
    return node


def slug(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def main():
    spec = to_30(copy.deepcopy(app.openapi()))
    spec["openapi"] = "3.0.3"
    spec["servers"] = [{"url": os.environ.get("PUBLIC_URL", get_settings().public_url)}]
    spec["security"] = [{"APIKeyHeader": []}]

    out = Path(__file__).resolve().parents[1] / "openapi"
    out.mkdir(exist_ok=True)
    (out / "safeone.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False),
                                      encoding="utf-8")

    tags = {t for ops in spec["paths"].values() for op in ops.values() for t in op.get("tags", [])}
    for tag in sorted(tags - {"Admin"}):
        sub = copy.deepcopy(spec)
        sub["info"]["title"] = f"SafeOne - {tag}"
        sub["paths"] = {}
        for path, ops in spec["paths"].items():
            kept = {m: op for m, op in ops.items() if tag in op.get("tags", [])}
            if kept:
                sub["paths"][path] = kept
        (out / f"{slug(tag)}.yaml").write_text(yaml.safe_dump(sub, allow_unicode=True, sort_keys=False),
                                               encoding="utf-8")
    print("Gerado em", out, sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main()

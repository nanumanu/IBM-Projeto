# SafeOne API

> **Versão usada no hackathon:** os agentes no watsonx Orchestrate, na pasta
> [`orchestrate/`](orchestrate/README.md), com as ferramentas em Python rodando dentro do
> próprio Orchestrate. Esta API não está publicada (o deploy no Code Engine descrito abaixo não
> é usado); ela fica como referência de como a aprovação humana seria garantida por permissão
> numa versão de produção.

Serviços que os agentes do SafeOne chamam como ferramentas no **watsonx Orchestrate**, para
identificar, prevenir e responder a fraudes em pagamentos olhando o padrão **de rede**: uma
conta que recebe de 14 instituições em duas horas parece normal para cada banco isoladamente,
mas o desenho aparece quando se soma o que todos veem.

```
Sentinela ──► Investigador ──► Decisão ──► [ANALISTA APROVA] ──► Resposta ──► Comunicação
    ▲                                                                              │
    └────────────────────────────── Aprendizado ◄── feedback do analista ◄─────────┘
```

**Nenhuma conta é bloqueada e nenhum valor é devolvido sem aprovação humana.** Isso é
garantido na própria API: as ações nascem `proposed`, e só a chave de analista executa.

## Rodar localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

No Windows (PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8080
```

Documentação interativa em http://localhost:8080/docs (clique em **Authorize** e use as
chaves `AGENT_API_KEY` / `ANALYST_API_KEY` do seu `.env`; sem `.env`, valem `dev-agent-key`
e `dev-analyst-key`). Na primeira execução o banco é populado com dados sintéticos.

Testes: `pytest -q`

## Dados sintéticos e roteiro da demo

326 contas em 14 instituições fictícias, ~3.300 transferências nos últimos 7 dias e três
cenários plantados (horários relativos ao momento em que a API sobe):

| Conta | Cenário | Resultado esperado |
|---|---|---|
| `ACC-900001` | Conta-laranja: aberta há 6 dias, recebe de 14 instituições em ~1h, repassa 90% para `ACC-900002`/`ACC-900003`, que repassam adiante. 4 contestações. | Score 100, recomenda bloquear e pedir devolução |
| `ACC-900010` | Padaria antiga que recebe de muitas instituições todo dia | Sinal de rede alto, mas **não abre caso** |
| `ACC-900020` | República: conta nova que recebe o aluguel de 6 moradores e paga o dono | Abre caso (score 65), analista rejeita: falso positivo que ensina o sistema |

Roteiro sugerido (todos os passos estão no Swagger):

1. `POST /monitoring/scan` — Sentinela encontra os dois casos.
2. `GET /accounts/ACC-900001/network` — Investigador mostra 14 instituições de origem e o rastro do dinheiro.
3. `POST /cases/{id}/dossier` — Decisão gera evidências, justificativa e ações propostas.
4. `POST /cases/{id}/decision` com a **chave de agente** → `403`. O agente não decide sozinho.
5. Mesma chamada com a **chave de analista** → conta bloqueada, devoluções solicitadas.
6. `POST /transactions` saindo de `ACC-900001` → retida (`held: true`).
7. `POST /cases/{id}/notifications` — mensagens para o titular e para as 4 vítimas.
8. `POST /cases/{id}/feedback` com `fraud`; no caso da república, `reject` + `legit`.
9. `GET /learning/weights` e `GET /metrics` — pesos ajustados, precisão, valor devolvido.

Para reiniciar a demo: `POST /admin/reset-demo` (chave de analista).

## Ferramentas por agente

| Agente | operationId | Rota |
|---|---|---|
| Sentinela | `ingest_transaction` | `POST /transactions` |
| | `open_dispute` | `POST /disputes` |
| | `scan_recent_activity` | `POST /monitoring/scan` |
| | `score_account` | `GET /accounts/{id}/risk` |
| | `get_account`, `list_transactions` | `GET /accounts/{id}`, `GET /transactions` |
| Investigador | `list_cases`, `get_case` | `GET /cases`, `GET /cases/{id}` |
| | `investigate_case` | `GET /cases/{id}/investigation` |
| | `get_account_network` | `GET /accounts/{id}/network` |
| Decisão | `build_case_dossier` | `POST /cases/{id}/dossier` |
| Resposta (analista) | `decide_case` | `POST /cases/{id}/decision` |
| Comunicação | `notify_parties`, `list_notifications` | `POST/GET /cases/{id}/notifications` |
| Aprendizado (analista) | `submit_feedback` | `POST /cases/{id}/feedback` |
| Aprendizado | `get_signal_weights`, `get_metrics` | `GET /learning/weights`, `GET /metrics` |

### Como o score funciona

Cinco sinais, cada um de 0 a 1 e sempre acompanhado da evidência em texto:

| Sinal | Peso inicial | O que mede |
|---|---|---|
| `network_fan_in` | 35 | Instituições distintas de origem na janela (só visível na infraestrutura) |
| `pass_through` | 25 | Quanto do que entrou já saiu |
| `new_account` | 15 | Idade da conta |
| `disputes` | 15 | Contestações em transferências recebidas |
| `inbound_spike` | 10 | Entrada comparada ao histórico da própria conta |

Score = média ponderada × 100. Acima de `CASE_THRESHOLD` (60) abre caso. No feedback, os
sinais que pesaram no caso (valor ≥ 0,5) sobem 10% se era fraude e descem 10% se era falso
positivo.

## Deploy no IBM Cloud Code Engine

```bash
ibmcloud login --sso
ibmcloud target -r us-south -g Default
ibmcloud ce project create --name safeone
ibmcloud ce application create --name safeone-api --build-source . --port 8080 \
  --min-scale 1 \
  --env AGENT_API_KEY=<gere-uma-chave> \
  --env ANALYST_API_KEY=<gere-outra-chave>
ibmcloud ce application get --name safeone-api   # mostra a URL pública
```

`--min-scale 1` evita que a aplicação escale para zero e perca o SQLite. Para persistência
real, use IBM Cloud Databases for PostgreSQL e defina `DATABASE_URL`.

Gere chaves fortes com `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Importar no watsonx Orchestrate

```bash
PUBLIC_URL=https://<url-do-code-engine> python scripts/export_openapi.py
```

Isso gera em `openapi/` a especificação completa (`safeone.yaml`) e uma por agente
(`sentinela.yaml`, `investigador.yaml`, `decisao.yaml`...), em OpenAPI 3.0.3. Importe cada
arquivo como ferramenta OpenAPI no agente correspondente, pela interface do Orchestrate ou
pelo ADK (`orchestrate tools import -k openapi -f openapi/sentinela.yaml`), configurando a
autenticação por API key no cabeçalho `X-API-Key`. Confira os comandos de conexão na
documentação do ADK, que muda com frequência.

Os agentes recebem só a **chave de agente**. `decide_case` e `submit_feedback` exigem a chave
de analista e devem ficar na interface do analista, não com os agentes.

## watsonx.ai (opcional)

Com `WATSONX_API_KEY` e `WATSONX_PROJECT_ID` definidos, a narrativa do dossiê é redigida por
um modelo Granite a partir dos fatos do caso. Sem eles (ou se a chamada falhar), usa texto de
template, então a demo nunca depende da disponibilidade do modelo.

## Estrutura

```
app/
  main.py              app FastAPI e inicialização
  config.py            variáveis de ambiente
  models.py            tabelas (contas, transferências, casos, ações, notificações...)
  schemas.py           contratos de entrada e saída
  security.py          chaves de agente e de analista
  seed.py              dados sintéticos
  routers/             rotas por agente
  services/
    scoring.py         Sentinela: sinais e score
    graph.py           Investigador: grafo de relacionamento
    dossier.py         Investigador + Decisão: contexto, dossiê, recomendação
    response.py        Resposta: execução após aprovação
    communication.py   Comunicação: mensagens
    learning.py        Aprendizado: ajuste de pesos e métricas
    watsonx.py         cliente watsonx.ai
scripts/export_openapi.py
tests/test_flow.py     fluxo completo, permissões, falso positivo
```

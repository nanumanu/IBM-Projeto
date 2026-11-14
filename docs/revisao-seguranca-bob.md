# Revisão de segurança do SafeOne

Escopo: `orchestrate/safeone_tools.py` e todos os arquivos de `app/`, mais `requirements.txt`,
`orchestrate/requirements.txt`, `.env.example` e o `README.md` no que toca a chaves e deploy.
Nenhum arquivo de código foi alterado nesta revisão: ela só registra os problemas e as
correções propostas.

Contexto considerado: `safeone_tools.py` roda dentro do IBM watsonx Orchestrate, com dados
sintéticos e sem persistência; a API em `app/` é a versão de referência, que controla quem
pode aprovar ações por chave de API no cabeçalho `X-API-Key`.

Três itens foram confirmados executando a API em memória (cliente de teste do FastAPI), sem
alterar nada: S3 (resposta 500), S6 (preflight de CORS aceito para qualquer origem) e S13
(`/docs` e `/openapi.json` respondem 200 sem chave). As vulnerabilidades do item S12 vieram de
uma consulta à base OSV (osv.dev) em 14/11/2026, com as versões fixadas nos dois
`requirements.txt`.

## Problemas encontrados

"Muda comportamento testado?" é **sim** quando a correção altera respostas, códigos HTTP,
textos de `display_text`, scores ou o fluxo coberto por `tests/test_flow.py` e pelos testes do
Orchestrate em `orchestrate/testes/`.

| ID | Arquivo e linha | Descrição | Severidade | Correção proposta | Muda comportamento testado? |
| --- | --- | --- | --- | --- | --- |
| S1 | `app/config.py:13-14`; `.env.example:5-6` | Chaves padrão no código (`dev-agent-key`, `dev-analyst-key`). Se a API subir sem `AGENT_API_KEY` e `ANALYST_API_KEY`, qualquer pessoa que leia o repositório ou o README aprova ações. O `.env.example` também traz valores fixos, que funcionam como chave se forem copiados sem troca. | Alta | Recusar a inicialização fora do ambiente de desenvolvimento quando as chaves forem as padrão, as do `.env.example`, iguais entre si ou curtas demais. | sim |
| S2 | `orchestrate/safeone_tools.py:452` (`record_analyst_decision`); `app/schemas.py:122` (`DecisionIn.analyst`) | No Orchestrate, a aprovação é um parâmetro (`approved`) preenchido pelo modelo de linguagem a partir do texto da conversa: não há credencial de analista, só as instruções dos agentes. Quem conseguir escrever na conversa, ou injetar texto nela, aprova um caso. Nas duas versões, o nome de quem decidiu é declarado por quem chama (`analyst_name`, `analyst`), não vem da credencial; na API há uma única chave de analista compartilhada, então o registro não prova quem decidiu. | Alta | Tirar a decisão do alcance do agente: a aprovação passa a ser uma chamada autenticada do analista (como `decide_case` na API), com identidade individual vinda da credencial e não do corpo do pedido. | sim |
| S3 | `app/security.py:11-12` (`_matches`) | `secrets.compare_digest` com `str` levanta `TypeError` quando a chave enviada tem caractere não ASCII. Um pedido sem autenticação com `X-API-Key: chave-é` recebe 500 em vez de 401, em qualquer rota protegida. Não dá acesso, mas permite gerar erros e ruído de log à vontade, e esconde tentativas de acesso atrás de erros de servidor. | Média | Comparar em bytes (`.encode("utf-8")`), o que mantém o tempo constante e aceita qualquer entrada. | não |
| S4 | `orchestrate/safeone_tools.py:504, 516` (`draft_notifications`); `:541` (`build_audit_record`) | As ferramentas confiam no que o chamador afirma: `case_approved=True` libera os avisos e `approved` define o que o registro de auditoria diz, sem conferir que houve decisão. Como nada persiste, a ferramenta não tem como conferir. A instrução da Comunicação aceita como prova um texto na conversa ("Decisão registrada no caso ...: aprovado por ..."), que o próprio usuário pode digitar. O registro de auditoria pode, assim, descrever uma decisão que nunca foi registrada. | Média | Persistir a decisão e fazer as ferramentas lerem o status gravado, em vez de receberem a aprovação como parâmetro (é o que a API faz em `communication.notify`). | sim |
| S5 | `orchestrate/safeone_tools.py:481` e `:580` (`decided_by`) | `analyst_name` entra em `display_text` e no registro de auditoria sem limite de tamanho e com quebras de linha preservadas. Um nome com `\n` forja linhas inteiras no bloco que os agentes copiam palavra por palavra (por exemplo, uma segunda linha "Decisão registrada no caso ...: aprovado por ..."), e um nome longo carrega instruções para o modelo. | Média | Reduzir o nome a uma linha e a 80 caracteres antes de usar. Nomes normais não mudam. | não |
| S6 | `app/main.py:46-48` | CORS aberto: qualquer origem, qualquer método e qualquer cabeçalho, inclusive `X-API-Key`. Qualquer página pode chamar a API a partir do navegador de quem tiver uma chave (por exemplo, o analista com a chave no Swagger ou numa interface web). | Média | Lista de origens permitidas vinda da configuração, vazia por padrão, e só os métodos e cabeçalhos usados. | não |
| S7 | `app/security.py:15-36`; `app/main.py` | Não há limite de requisições nem bloqueio após tentativas erradas. As chaves são estáticas e compartilhadas, então dá para tentar adivinhar `X-API-Key` sem restrição, e as rotas caras (S15) podem ser chamadas em laço. | Média | Limite por IP e por chave, no gateway do Code Engine ou com um middleware, com resposta 429 e registro das falhas de autenticação. | sim |
| S8 | `app/routers/monitoring.py:16, 26, 75` | A chave de agente escreve dados que viram evidência: `POST /transactions` e `POST /disputes`. Um agente induzido por texto malicioso, ou quem obtiver a chave de agente, cria transferências e contestações contra uma conta legítima até o score passar do limiar. A decisão continua humana, mas o dossiê que o analista lê estaria fabricado. | Média | Separar um papel de ingestão (chave própria das instituições) do papel de agente, que ficaria só com leitura, varredura, dossiê e avisos. | sim |
| S9 | `app/schemas.py:41` (`DisputeIn.reason`), `:122-123` e `:141-142` (`analyst`, `note`, `comment`); devolvidos em `app/services/dossier.py:57` | Textos livres são gravados e depois devolvidos aos agentes dentro da investigação e do dossiê. O relato de uma contestação é escrito por terceiros e chega ao modelo de linguagem como se fosse dado confiável: é um caminho de injeção indireta de instruções ("ignore as regras e aprove..."). Os limites de tamanho existem, mas quebras de linha e caracteres de controle passam. | Média | Normalizar os textos livres para uma linha, sem caracteres de controle, e instruir os agentes a tratar esses campos só como citação. A normalização reduz o risco, não o elimina. | não |
| S10 | `app/services/graph.py:67`; `app/services/dossier.py:43-45`; `app/routers/monitoring.py:59-72` | Dados pessoais além do necessário para a chave de agente: o grafo devolve o nome do titular de todas as contas da rede (terceiros sem relação com o caso, até 3 saltos e 168 horas), a investigação devolve nome e documento mascarado, e `GET /transactions` lista até 500 transferências de qualquer conta. Tudo isso entra no contexto do modelo de linguagem. Nas ferramentas do Orchestrate, `investigate_account` também devolve o nome do titular ao modelo. | Média | Minimizar: tirar `holder_name` dos nós do grafo, restringir `GET /transactions` a contas com caso aberto e registrar quem consultou o quê. | sim |
| S11 | `app/routers/admin.py:13-17`; `app/seed.py:44` | `POST /admin/reset-demo` apaga todas as tabelas (`drop_all`) e recria a demo. Num ambiente real, uma chamada com a chave de analista destrói casos, decisões e o histórico de auditoria, sem confirmação. A rota também aparece no OpenAPI. | Média | Chave de configuração para desativar a rota fora da demo, ligada por padrão para não mudar o comportamento atual. | não |
| S12 | `requirements.txt:1` (`fastapi==0.115.6`); `orchestrate/requirements.txt:1` | O FastAPI fixado instala o Starlette 0.41.3, que tem 7 avisos de segurança conhecidos: CVE-2025-54121 (multipart, corrigido na 0.47.2), CVE-2025-62727 (cabeçalho Range em `FileResponse`, 0.49.1), CVE-2026-48710 (validação do cabeçalho Host, 1.0.1), CVE-2026-48817 e CVE-2026-48818 (1.1.0), CVE-2026-54282 (1.3.0) e CVE-2026-54283 (limites de formulário, 1.3.1). A exposição prática é baixa: a API não recebe formulários nem arquivos, não usa `StaticFiles`, `FileResponse` nem `HTTPEndpoint`, e não decide permissão pelo caminho da URL. As dependências transitivas (Starlette, h11, anyio) não estão fixadas, então cada instalação pode trazer versões diferentes. Para as demais versões fixadas, incluindo `ibm-watsonx-orchestrate==2.19.1`, a consulta não devolveu avisos. | Média | Atualizar o FastAPI para uma versão que aceite Starlette corrigido (1.3.1 ou superior), fixar as transitivas com um arquivo de travamento e rodar uma checagem de dependências na integração. `orchestrate/requirements.txt` não deve ser alterado nesta etapa. | sim |
| S13 | `app/main.py:40-45` | `/docs`, `/redoc` e `/openapi.json` respondem sem chave. Qualquer pessoa vê todas as rotas, parâmetros e quais exigem chave de analista. | Baixa | Chave de configuração para desligar a documentação em produção, ligada por padrão. | não |
| S14 | `app/models.py:64`; `app/routers/monitoring.py:83-86`; `app/services/response.py:29-49` | Verificação e gravação separadas, sem trava. Duas contestações simultâneas da mesma transferência passam pelo `select` e entram as duas, inflando o sinal de contestações (não há restrição de unicidade em `disputes.transaction_id`). Em `decide`, duas decisões simultâneas do mesmo caso podem ser aplicadas no PostgreSQL. | Baixa | Restrição de unicidade em `Dispute.transaction_id` com tratamento do erro como 409, e `SELECT ... FOR UPDATE` no caso antes de decidir. | não |
| S15 | `app/schemas.py:13-14, 40, 124`; `app/services/graph.py:18`; `app/routers/cases.py:65-66` | Faltam limites: identificadores sem tamanho máximo no corpo dos pedidos, `action_ids` sem limite de itens e nenhum limite de tamanho do corpo. `get_account_network` carrega na memória todas as transferências da janela (até 168 horas) a cada chamada, e `scan` faz várias consultas por conta: são rotas caras que a chave de agente pode repetir. | Baixa | `max_length` nos identificadores e em `action_ids`; depois, filtrar o grafo no banco e limitar o corpo no servidor. | não |
| S16 | `README.md:84-85` | O deploy documentado passa as chaves com `--env` na linha de comando: elas ficam no histórico do terminal e legíveis na configuração da aplicação. Não há orientação de rotação. | Baixa | Documentar o uso de segredos do Code Engine e a troca periódica das chaves. | não |
| S17 | `app/services/dossier.py:148, 163` | O texto gerado pelo watsonx.ai entra no dossiê sem limite de tamanho nem validação. Os fatos enviados ao modelo são gerados pelo sistema, então a entrada é controlada, mas a saída pode trazer afirmações que não estão nos fatos e é mostrada ao analista junto das evidências. | Baixa | Limitar o tamanho da narrativa e manter `narrative_source` visível para o analista. | não |

## Correções que não mudam o comportamento testado

Trechos exatos propostos. Nenhum foi aplicado.

### S3: comparar a chave em bytes

`app/security.py`, função `_matches`:

```python
def _matches(given: str | None, expected: str) -> bool:
    return given is not None and secrets.compare_digest(
        given.encode("utf-8"), expected.encode("utf-8")
    )
```

### S5: nome do analista em uma linha e com limite

`orchestrate/safeone_tools.py`, nas duas linhas que definem `decided_by`
(`record_analyst_decision` e `build_audit_record`):

```python
    decided_by = " ".join(analyst_name.split())[:80] or "analista (nome não informado)"
```

Para um nome comum ("Manuela") o resultado é idêntico, e o texto padrão continua exatamente
"analista (nome não informado)". Esta correção toca uma função já publicada no Orchestrate,
então depende da triagem do grupo e de rodar `orchestrate/testes/rodar_testes.py` depois.

### S6: CORS restrito por configuração

`app/config.py`, dentro de `Settings`:

```python
    # Origens que podem chamar a API pelo navegador, separadas por vírgula. Vazio = nenhuma.
    cors_origins: str = ""
```

`app/main.py`, no lugar do `add_middleware` atual:

```python
_origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)
```

Os testes e os agentes do Orchestrate chamam a API de servidor para servidor, sem CORS. A tela
`/docs` continua funcionando, porque é servida pela mesma origem.

### S9: textos livres em uma linha

`app/schemas.py`:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _one_line(v: str | None) -> str | None:
    # tira quebras de linha e caracteres de controle de textos que depois chegam aos agentes
    return v if v is None else " ".join("".join(c for c in v if c.isprintable() or c.isspace()).split())


class DisputeIn(BaseModel):
    transaction_id: str
    reason: str = Field(max_length=200, description="Relato do cliente, ex.: 'golpe do falso parente'")

    _clean = field_validator("reason")(_one_line)
```

O mesmo validador vale para `analyst` e `note` em `DecisionIn` e para `analyst` e `comment` em
`FeedbackIn`:

```python
    _clean = field_validator("analyst", "note")(_one_line)      # em DecisionIn
    _clean = field_validator("analyst", "comment")(_one_line)   # em FeedbackIn
```

### S11: desativar o reset fora da demo

`app/config.py`, dentro de `Settings`:

```python
    demo_reset_enabled: bool = True       # em produção, defina DEMO_RESET_ENABLED=false
```

`app/routers/admin.py`:

```python
from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings


def reset_demo(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Recria o cenário da demo com horários relativos a agora. Exige chave de analista."""
    if not settings.demo_reset_enabled:
        raise HTTPException(404, "Rota desativada neste ambiente.")
    return reset_and_seed(db)
```

Com o valor padrão, as respostas 401 e 403 testadas em
`test_analyst_route_without_key_is_401` continuam iguais.

### S13: documentação desligável

`app/config.py`, dentro de `Settings`:

```python
    docs_enabled: bool = True             # em produção, defina DOCS_ENABLED=false
```

`app/main.py`:

```python
_docs = get_settings().docs_enabled
app = FastAPI(
    title="SafeOne API",
    version="1.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
```

`scripts/export_openapi.py` usa `app.openapi()` direto, sem passar pela rota. Vale confirmar
que a exportação continua funcionando com `DOCS_ENABLED=false` antes de adotar.

### S14: contestação única por transferência

`app/models.py`, em `Dispute`:

```python
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), unique=True)
```

`app/routers/monitoring.py`, em `open_dispute`, no lugar de `db.add(d)` e `db.flush()`:

```python
from sqlalchemy.exc import IntegrityError

    db.add(d)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Transferência {tx.id} já foi contestada.")
```

A resposta 409 já é a testada em `test_same_transaction_cannot_be_disputed_twice`. A restrição
só passa a existir em bancos recriados: um banco já existente precisa de migração. A trava em
`decide` (`with_for_update`) fica para depois, porque precisa de teste com PostgreSQL.

### S15: limites de tamanho

`app/schemas.py`:

```python
class TransactionIn(BaseModel):
    source_account_id: str = Field(max_length=32, description="Conta de origem")
    dest_account_id: str = Field(max_length=32, description="Conta de destino")


class DisputeIn(BaseModel):
    transaction_id: str = Field(max_length=32)


class DecisionIn(BaseModel):
    action_ids: list[str] | None = Field(
        default=None, max_length=50,
        description="Aprovar só estas ações. Omitido = todas as ações propostas.",
    )
```

Os 32 caracteres são o tamanho das colunas em `app/models.py`. Os demais campos de cada classe
ficam como estão.

### S16: segredos no deploy

`README.md`, na seção de deploy, no lugar dos dois `--env` de chave:

```bash
ibmcloud ce secret create --name safeone-keys \
  --from-literal AGENT_API_KEY=<gere-uma-chave> \
  --from-literal ANALYST_API_KEY=<gere-outra-chave>
ibmcloud ce application create --name safeone-api --build-source . --port 8080 \
  --min-scale 1 --env-from-secret safeone-keys
```

Os comandos do `ibmcloud ce` mudam entre versões: confira na documentação antes de publicar.

### S17: limite na narrativa

`app/services/dossier.py`, em `build_dossier`:

```python
    narrative = (watsonx.generate_narrative(facts) or "")[:1500] or None
```

Nos testes o watsonx.ai não está configurado e o dossiê usa o texto de template, então nada
muda.

## Correções que mudam o comportamento testado

Risco de aplicar agora, item por item.

- **S1 (chaves padrão).** `tests/conftest.py` usa `dev-agent-key` e `dev-analyst-key` sem
  definir variáveis de ambiente, e o README diz que essas chaves valem sem `.env`. Recusar as
  chaves padrão quebra os 13 testes da API e o passo de rodar localmente. Precisa vir junto
  com uma mudança no `conftest.py` e no README, e com um jeito explícito de marcar o ambiente
  de desenvolvimento.
- **S2 (aprovação como parâmetro do agente).** É a limitação já declarada em
  `orchestrate/README.md`. Corrigir significa tirar `record_analyst_decision` do agente Decisão
  e mudar as instruções do SafeOne, ou seja, o roteiro da demo e os testes do plano
  (aprovação, rejeição e os avisos que dependem do texto "Decisão registrada"). Não cabe antes
  da apresentação; deve ser explicado como limitação e desenhado para a versão de produção.
- **S4 (ferramentas confiam em `case_approved` e `approved`).** A correção depende de
  persistência, que a versão no Orchestrate não tem por projeto. Trocar a assinatura de
  `draft_notifications` muda as instruções da Comunicação e os testes de avisos. Vale junto
  com o S2.
- **S7 (limite de requisições).** Introduz respostas 429 em rotas testadas e uma dependência
  nova. Um limite mal calibrado derruba `test_ingestion_opens_case_in_real_time`, que faz
  várias chamadas seguidas, e a varredura da demo. Mais seguro aplicar no gateway, fora do
  código, e medir antes.
- **S8 (agente grava transferências e contestações).** Os testes usam a chave de agente para
  `POST /transactions` e `POST /disputes`. Criar um papel de ingestão muda os códigos HTTP
  dessas rotas para a chave de agente (403) e a divisão de ferramentas por agente descrita no
  README e no OpenAPI exportado.
- **S10 (dados pessoais em excesso).** Tirar campos das respostas muda o contrato de rotas
  testadas (`/accounts/{id}/network`, investigação e dossiê) e o OpenAPI que seria importado
  no Orchestrate. Precisa de uma revisão do que cada agente de fato usa antes de cortar.
- **S12 (dependências).** Atualizar o FastAPI atravessa várias versões e uma versão maior do
  Starlette. O esperado é que as respostas não mudem, mas isso só fica demonstrado rodando os
  13 testes da API com as versões novas, e o Dockerfile instala o mesmo `requirements.txt`.
  Como a exposição prática é baixa, dá para fazer num branch separado, depois da apresentação.
  `orchestrate/requirements.txt` fica como está: ele vai junto na importação das ferramentas e
  os testes do plano foram feitos com o ADK 2.19.1.

## Verificado, sem problema encontrado

- **Injeção de SQL.** Todas as consultas usam o ORM do SQLAlchemy com parâmetros; não há SQL
  montado com texto do usuário.
- **Chave de agente não aprova.** `require_analyst` devolve 403 para a chave de agente em
  `decide_case`, `submit_feedback` e `reset_demo`, e isso está coberto por testes. As ações
  nascem `proposed` e só `response.decide` as executa.
- **Avisos antes da aprovação.** A API responde 409 e a ferramenta do Orchestrate devolve erro
  sem mensagens.
- **Erros internos.** As mensagens de erro da API trazem só o identificador pedido e o status
  do caso; não há rastro de pilha nem detalhe de banco nas respostas.
- **Segredos no repositório.** `.env` e `*.db` estão no `.gitignore` e no `.dockerignore`; a
  chave do watsonx.ai vem só de variável de ambiente e é enviada no corpo do pedido de token,
  não na URL.
- **Contêiner.** O Dockerfile roda com usuário sem privilégios.
- **Documento do titular.** O modelo guarda só o documento mascarado.
- **Código perigoso.** Não há `eval`, `exec`, `pickle`, `subprocess` nem leitura de arquivo a
  partir de entrada do usuário em `app/` ou em `safeone_tools.py`; a exportação usa
  `yaml.safe_dump`.
- **Ferramentas do Orchestrate.** Não fazem chamadas de rede nem gravam em disco; contas
  inexistentes são recusadas por `_check_account` antes de qualquer uso do identificador.

# Tarefas para o IBM Bob

Roteiro para a pessoa do grupo que vai operar o IBM Bob. São 4 tarefas, nesta ordem. Cada
uma traz o objetivo, os arquivos envolvidos, o prompt para colar no Bob, o critério de pronto
e as capturas de tela que servem de evidência.

O código e os documentos destas tarefas devem ser escritos **pelo Bob**. Este arquivo só
prepara o trabalho; a revisão, os testes e a integração vêm depois.

## Regras para todas as tarefas

1. **Trabalhe só no branch `bob`.** Antes de abrir o Bob:
   ```bash
   git fetch origin
   git checkout bob
   git pull
   ```
   Nada vai para o `main` e nada é importado no Orchestrate nesta etapa.
2. **Abra no Bob a pasta raiz do repositório** (`IBM-Projeto`), para ele enxergar `app/`,
   `orchestrate/` e `tests/`.
3. **Um commit por tarefa, com o prefixo `Bob:`**, por exemplo
   `Bob: tarefa 1 - documento de arquitetura`. Assim a revisão separa o que o Bob fez do que
   for corrigido depois. Se você editar algo à mão, faça um commit separado, sem o prefixo, e
   diga o que mudou.
4. **Não deixe o Bob mexer em**:
   - `orchestrate/agentes/*.yaml` (são os agentes publicados);
   - `orchestrate/requirements.txt` (vai junto na importação das ferramentas para o Orchestrate);
   - `orchestrate/testes/` (o executor dos testes do plano).

   Se o Bob propuser mudar algum desses, recuse e anote a proposta no commit da tarefa.
5. **Não rode `orchestrate tools import`, `orchestrate agents import` nem `deploy`.**
6. **Evidências**: salve as capturas em `docs/evidencias-bob/`, em PNG, com o nome
   `tN-MM-descricao.png` (por exemplo `t1-01-prompt-architect.png`). Em toda captura deve
   aparecer a interface do Bob com o modo selecionado. Faça commit das capturas junto com a
   tarefa.
7. Se o Bob pedir para aprovar a execução de um comando ou a escrita de um arquivo, leia antes
   de aprovar. Comandos que só leem ou rodam `pytest` podem ser aprovados; qualquer coisa que
   instale, apague ou faça `git push` deve ser negada.

### Preparar o ambiente para as tarefas 3 e 4

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -r orchestrate/requirements.txt
python -m pytest -q                    # deve dar 13 passed antes de começar
```

---

## Tarefa 1 — Documento de arquitetura (modo Architect)

**Objetivo.** Gerar `docs/arquitetura.md`, que explica a solução para quem não conhece o
código: os 6 agentes, as 7 ferramentas, onde fica a aprovação humana e o papel da API de
referência, com um diagrama em Mermaid.

**Arquivos que o Bob deve ler:** `orchestrate/README.md`, `orchestrate/safeone_tools.py`,
`orchestrate/agentes/*.yaml`, `README.md`, `app/security.py`, `app/routers/`.

**Arquivo que o Bob cria:** `docs/arquitetura.md` (só esse).

**Modo do Bob:** Architect.

**Prompt para colar no Bob:**

```text
Você está no repositório do SafeOne, um sistema de agentes no IBM watsonx Orchestrate que detecta
fraudes em pagamentos olhando o padrão de rede (uma conta que recebe de muitas instituições em
pouco tempo e repassa o dinheiro rápido).

Leia orchestrate/README.md, orchestrate/safeone_tools.py, todos os arquivos em orchestrate/agentes/,
o README.md da raiz, app/security.py e a pasta app/routers/.

Crie o arquivo docs/arquitetura.md, em português, com estas seções:

1. Visão geral: o problema e a ideia da solução em até 2 parágrafos.
2. Agentes: uma tabela com os 6 agentes (SafeOne orquestrador, Sentinela, Investigador, Decisão,
   Comunicação, Aprendizado), dizendo o papel de cada um, as ferramentas que ele usa e para quem
   ele passa o caso. Tire essas informações dos campos tools, collaborators e instructions dos
   arquivos YAML, não invente.
3. Ferramentas: uma tabela com as 7 funções marcadas com @tool em safeone_tools.py, com
   parâmetros, o que devolvem e qual agente as usa. Explique que os dados são sintéticos,
   recriados de forma determinística a cada chamada, e que cada ferramenta devolve um campo
   display_text com o texto pronto para o analista.
4. Aprovação humana: explique em que ponto do fluxo o analista aprova ou rejeita, qual
   ferramenta registra a decisão, e como as instruções dos agentes impedem ações e avisos sem
   aprovação. Explique também como a API de referência em app/ garante isso por permissão
   (chave de agente recebe 403 nas rotas de analista).
5. API de referência: o que ela é, que ela não é a versão usada no Orchestrate hoje, e o que
   ela mostra que a versão no Orchestrate não tem (persistência e controle por chave).
6. Cenários de demonstração: ACC-900001 (conta-laranja), ACC-900010 (loja legítima, não abre
   caso) e ACC-900020 (república de estudantes, falso positivo).
7. Limitações conhecidas, tiradas da seção de limitações do orchestrate/README.md.

Inclua um diagrama em Mermaid (flowchart) que mostre: o analista conversando com o SafeOne, o
SafeOne chamando os 5 agentes colaboradores, cada agente ligado às suas ferramentas, e o ponto
de aprovação humana destacado entre Decisão e as ações/Comunicação. Use só nomes que existem
no código. Confira que o bloco Mermaid tem sintaxe válida.

Não altere nenhum outro arquivo.
```

**Critério de pronto:**
- `docs/arquitetura.md` existe e tem as 7 seções.
- As tabelas listam exatamente 6 agentes e 7 ferramentas (`scan_recent_activity`,
  `score_account`, `investigate_account`, `build_case_dossier`, `record_analyst_decision`,
  `draft_notifications`, `record_feedback`), com os agentes certos para cada uma.
- O diagrama Mermaid renderiza sem erro (abra o arquivo no GitHub depois do push, ou cole o
  bloco em https://mermaid.live).
- Nenhum outro arquivo foi alterado (`git status` mostra só o novo arquivo e as capturas).

**Evidências (`docs/evidencias-bob/`):**
- `t1-01-prompt-architect.png`: o prompt colado, com o modo Architect visível.
- `t1-02-plano-bob.png`: o plano ou a resposta do Bob antes de gerar o arquivo.
- `t1-03-arquivo-gerado.png`: o `docs/arquitetura.md` aberto no editor.
- `t1-04-diagrama.png`: o diagrama Mermaid renderizado (preview do editor, GitHub ou mermaid.live).

---

## Tarefa 2 — Revisão de segurança

**Objetivo.** O Bob revisa as ferramentas do Orchestrate e a API de referência e lista os
problemas de segurança. Nesta tarefa ele **só registra** os problemas e as correções
propostas; nada é corrigido ainda.

**Arquivos que o Bob deve ler:** `orchestrate/safeone_tools.py` e toda a pasta `app/`.

**Arquivo que o Bob cria:** `docs/revisao-seguranca-bob.md`.

**Modo do Bob:** um modo só de leitura (Ask ou Architect) ou o recurso de revisão de código
do Bob, se a sua versão tiver. Não use o modo Code nesta etapa, para o Bob não sair aplicando
correções.

**Prompt para colar no Bob:**

```text
Faça uma revisão de segurança de orchestrate/safeone_tools.py e de todos os arquivos em app/
(uma API FastAPI). Contexto: safeone_tools.py roda dentro do IBM watsonx Orchestrate, com dados
sintéticos; a API em app/ é a versão de referência, que controla quem pode aprovar ações por
chave de API (chave de agente e chave de analista, no cabeçalho X-API-Key).

Procure, entre outros: autenticação e autorização (alguém sem a chave de analista consegue
executar ou aprovar ações?), validação de entrada (identificadores de conta, valores, textos
livres como analyst_name), injeção (SQL, texto que chega ao modelo de linguagem), vazamento de
dados ou de detalhes internos em mensagens de erro, segredos e chaves padrão no código ou na
configuração, CORS, limites de tamanho e de requisições, dependências desatualizadas em
requirements.txt e orchestrate/requirements.txt.

NÃO altere nenhum arquivo de código. Crie apenas o arquivo docs/revisao-seguranca-bob.md, em
português, com uma tabela em que cada linha é um problema e as colunas são:
ID (S1, S2...), arquivo e linha, descrição, severidade (alta, média, baixa), correção proposta,
e "muda comportamento testado?" (sim ou não). Considere que muda o comportamento testado
qualquer correção que altere respostas, códigos HTTP, textos de display_text, scores ou o fluxo
coberto por tests/test_flow.py e pelos testes do Orchestrate em orchestrate/testes/.

Depois da tabela, para cada item com "muda comportamento testado? = não", mostre o trecho de
código exato da correção proposta. Para os itens com "sim", explique o risco de aplicar agora.
```

**Critério de pronto:**
- `docs/revisao-seguranca-bob.md` existe, com a tabela completa e a coluna
  "muda comportamento testado?" preenchida em todas as linhas.
- Nenhum arquivo de código foi alterado (`git diff --stat` só mostra o novo documento).

**Tarefa 2b (opcional, só depois da triagem).** As correções que o Bob propôs são revisadas
antes de qualquer aplicação. Quando o grupo indicar quais itens podem ser aplicados (só os
marcados com "não"), use o modo Code com este prompt, trocando a lista de IDs:

```text
Aplique apenas as correções S?, S? e S? descritas em docs/revisao-seguranca-bob.md, exatamente
como propostas. Não altere textos de display_text, scores, códigos HTTP de respostas já testadas
nem nenhum outro item. Depois rode `python -m pytest -q` na raiz e mostre o resultado. Ao
final, marque na tabela de docs/revisao-seguranca-bob.md quais itens foram aplicados.
```

Faça o commit da 2b separado, como `Bob: tarefa 2b - correções aplicadas S?, S?`.

**Evidências (`docs/evidencias-bob/`):**
- `t2-01-prompt-revisao.png`: o prompt colado, com o modo visível.
- `t2-02-achados.png`: a resposta do Bob com a lista de problemas (uma ou mais capturas,
  `t2-02a`, `t2-02b`... se não couber numa tela).
- `t2-03-relatorio.png`: o `docs/revisao-seguranca-bob.md` aberto no editor.
- Se fizer a 2b: `t2-04-correcoes-diff.png` (o diff das correções) e
  `t2-05-pytest.png` (o pytest passando depois delas).

---

## Tarefa 3 — Nova ferramenta `build_audit_record` (modo Code)

**Objetivo.** O Bob cria uma oitava ferramenta, `build_audit_record`, que gera o registro
padronizado de auditoria de um caso, para o agente Comunicação. Ela **não** será ligada ao
agente nem importada no Orchestrate nesta etapa.

**Arquivo envolvido:** `orchestrate/safeone_tools.py` (só acrescentar; nada do que existe
deve mudar).

**Modo do Bob:** Code.

**Prompt para colar no Bob:**

```text
Leia orchestrate/safeone_tools.py inteiro antes de começar. Ele contém 7 ferramentas Python do
IBM watsonx Orchestrate (ADK 2.19.1), marcadas com @tool, que seguem um padrão comum:
- recriam os dados sintéticos com _build_world() a cada chamada (determinístico, seed fixa);
- validam a conta com _check_account();
- reaproveitam as funções internas (_assess, _network, _dossier) em vez de recalcular;
- formatam dinheiro com _brl() e números com _num() (vírgula decimal);
- devolvem um dict com os dados e um campo display_text, o texto pronto em português que o
  agente copia para o analista;
- têm docstring no formato Google (Args/Returns), em português, porque o Orchestrate usa a
  docstring como descrição da ferramenta para o modelo.

Acrescente uma nova ferramenta no final da seção "Comunicação", logo depois de
draft_notifications:

    build_audit_record(account_id: str, approved: bool, analyst_name: str = "") -> dict

Ela gera o registro padronizado de auditoria de um caso já decidido pelo analista. Requisitos:
1. Mesmo padrão das outras ferramentas (lista acima). Não altere nenhuma função existente,
   nenhum texto de display_text existente, nem as constantes já definidas.
2. Crie uma constante RULES_VERSION no bloco de configuração (por exemplo "2026.11-v2") e
   use-a no registro como a versão das regras de score.
3. O registro deve conter: case_id (no formato CASO-<número>, como nas outras ferramentas),
   account_id, decisão (aprovado ou rejeitado), quem decidiu, quando (data e hora em UTC, no
   formato ISO 8601, a partir do "now" de _build_world), score e limiar, a recomendação do
   dossiê, as evidências (só os sinais com valor > 0, com rótulo e texto de evidência), as
   ações com o status final (executada se aprovado, descartada se rejeitado, igual a
   record_analyst_decision), o valor total de devolução solicitado, a versão das regras e os
   pesos dos sinais usados.
4. Quem decidiu: se analyst_name vier vazio ou só com espaços, use exatamente
   "analista (nome não informado)", como em record_analyst_decision.
5. Se a conta não tiver caso aberto (score abaixo do limiar, como a ACC-900010), não gere
   registro: devolva um dict com "error" explicando que não há caso aberto, no mesmo estilo de
   draft_notifications.
6. Conta inexistente deve levantar o mesmo ValueError das outras ferramentas (use _check_account).
7. display_text: um bloco em português, uma informação por linha, começando com
   "Registro de auditoria do caso CASO-...", com valores em reais no formato R$ 1.234,56 e
   números com vírgula decimal. O registro é interno, para auditoria: deixe isso claro na
   docstring, porque ele traz score e evidências que nunca podem ir para o titular da conta.
8. Inclua um campo "note" dizendo que é uma simulação da POC e que o registro não fica gravado
   entre conversas, como nas outras ferramentas.
9. Docstring em português, no formato Google, deixando claro que a ferramenta só deve ser usada
   depois que a decisão do analista foi registrada.

Não mexa em orchestrate/agentes/, orchestrate/requirements.txt nem orchestrate/testes/. Não
rode nenhum comando "orchestrate". Quando terminar, rode este comando na raiz do repositório e
mostre a saída:

    python -c "import sys; sys.path.insert(0, 'orchestrate'); import safeone_tools as t; [print((c := t.build_audit_record(a, ok, 'Manuela').content).get('display_text') or c, end='\n\n') for a, ok in [('ACC-900001', True), ('ACC-900020', False), ('ACC-900010', True)]]"
```

**Critério de pronto:**
- `git diff main -- orchestrate/safeone_tools.py` mostra só acréscimos (a função nova e a
  constante `RULES_VERSION`), nenhuma linha existente alterada ou removida.
- O comando final roda sem erro e mostra: registro com 7 ações executadas para a ACC-900001,
  registro de rejeição para a ACC-900020, e erro de "sem caso aberto" para a ACC-900010.
- `python -m pytest -q` na raiz continua com 13 passed.

**Evidências (`docs/evidencias-bob/`):**
- `t3-01-prompt-code.png`: o prompt colado, com o modo Code visível.
- `t3-02-codigo-gerado.png`: o diff ou o código da função nova no editor.
- `t3-03-saida-comando.png`: a saída do comando de verificação no terminal.

---

## Tarefa 4 — Testes unitários das ferramentas (modo Code)

**Objetivo.** O Bob escreve testes com pytest para as ferramentas, cobrindo os três cenários
e a ferramenta nova, que rodam localmente sem conexão com o Orchestrate.

**Arquivos envolvidos:** cria `orchestrate/tests/test_tools.py` (e, se precisar,
`orchestrate/tests/conftest.py`). Lê `orchestrate/safeone_tools.py`,
`orchestrate/README.md` e `orchestrate/testes/verificar.py` (só para conhecer os valores
esperados).

**Modo do Bob:** Code.

**Prompt para colar no Bob:**

```text
Crie testes unitários com pytest para as ferramentas de orchestrate/safeone_tools.py, no arquivo
orchestrate/tests/test_tools.py.

Importante sobre o ADK 2.19.1 do watsonx Orchestrate: as funções decoradas com @tool, quando
chamadas diretamente no Python, devolvem um objeto ToolResponse, e o dict retornado pela
função fica em .content. Exemplo: t.score_account("ACC-900001").content["score"]. Já os erros
(por exemplo conta inexistente) não são embrulhados: a chamada levanta ValueError direto.
Confirme isso rodando uma chamada antes de escrever os testes.

Os testes devem importar o módulo adicionando a pasta orchestrate ao sys.path (num conftest.py
em orchestrate/tests/ ou no topo do arquivo de teste) e devem passar tanto com
`python -m pytest -q orchestrate/tests` quanto com `python -m pytest -q` na raiz do repositório,
sem quebrar os testes que já existem em tests/. Não crie __init__.py em orchestrate/tests se isso
causar conflito de nome com o pacote tests/ da raiz.

Cubra pelo menos:
1. ACC-900001 (conta-laranja): score 100, acima do limiar; build_case_dossier recomenda
   bloquear_e_recuperar com as ações A1 a A7 e status aguardando_aprovacao_do_analista;
   investigate_account mostra o dinheiro indo para a ACC-900002 e depois para a ACC-900004;
   record_analyst_decision aprovado executa as 7 ações; draft_notifications com
   case_approved=True gera 1 mensagem para o titular e 4 para vítimas.
2. ACC-900010 (loja legítima): score 42, abaixo do limiar, recomendação monitorar, nenhuma ação
   proposta, e draft_notifications devolve erro (sem caso aberto).
3. ACC-900020 (república, falso positivo): score 65, acima do limiar; record_analyst_decision
   com approved=False descarta todas as ações; record_feedback com was_fraud=False leva o score
   de 65 para 63,2 (display_text com vírgula decimal).
4. scan_recent_activity: a ACC-900001 é o primeiro caso, a ACC-900020 aparece e a ACC-900010 não.
5. Proteções: draft_notifications com case_approved=False não gera mensagens; conta inexistente
   (ACC-123) levanta ValueError em score_account, investigate_account, build_case_dossier,
   record_analyst_decision, record_feedback e build_audit_record.
6. build_audit_record: para ACC-900001 aprovado, decisão aprovado, quem decidiu, 7 ações
   executadas, versão das regras igual a RULES_VERSION, data em ISO 8601 e display_text começando
   com "Registro de auditoria do caso CASO-900001"; para ACC-900020 rejeitado, todas as ações
   descartadas; para ACC-900010, erro de caso não aberto; analyst_name vazio vira
   "analista (nome não informado)".
7. Determinismo: duas chamadas seguidas devolvem o mesmo score e as mesmas ações.
8. Formato: todo display_text é str não vazia e os valores em dinheiro usam o formato "R$ 1.234,56".

Não compare horários exatos (os dados são relativos ao momento atual). Não altere
orchestrate/safeone_tools.py; se algum teste falhar por um problema da ferramenta, não mude a
ferramenta: marque o teste com um comentário explicando o problema e me avise.
Não altere orchestrate/requirements.txt (ele é enviado ao Orchestrate). Se precisar documentar
a dependência do pytest, crie orchestrate/requirements-dev.txt.

No final, rode `python -m pytest -q orchestrate/tests -v` e `python -m pytest -q` na raiz e
mostre as duas saídas.
```

**Critério de pronto:**
- `python -m pytest -q orchestrate/tests -v` passa, com testes para os 3 cenários, as
  proteções e a ferramenta nova.
- `python -m pytest -q` na raiz passa: os 13 testes da API mais os novos.
- `orchestrate/safeone_tools.py` e `orchestrate/requirements.txt` não foram alterados nesta
  tarefa.

**Evidências (`docs/evidencias-bob/`):**
- `t4-01-prompt-code.png`: o prompt colado, com o modo Code visível.
- `t4-02-testes-gerados.png`: o `test_tools.py` aberto no editor.
- `t4-03-pytest-orchestrate.png`: a saída de `pytest -v orchestrate/tests`, com todos passando.
- `t4-04-pytest-raiz.png`: a saída de `pytest -q` na raiz.

---

## Ao terminar

1. Confira que há 4 commits `Bob:` (ou 5, com a 2b) e as capturas em `docs/evidencias-bob/`.
2. Envie o branch: `git push origin bob`.
3. Anote, para o relatório, qualquer coisa que o Bob errou e você corrigiu à mão, qualquer
   proposta dele que você recusou e quanto do saldo do Bob cada tarefa consumiu, se a interface
   mostrar.
4. Avise que o Bob terminou. A revisão roda os testes da API, os testes novos e o
   `orchestrate/testes/rodar_testes.py`; este último precisa da chave do Orchestrate, então
   alguém com acesso ao ambiente `safeone` roda e envia a pasta `testes/resultados/<data-hora>`.

Os próximos passos (importar a ferramenta, ligar ao agente Comunicação, publicar e fazer merge
no `main`) só acontecem depois da revisão e da aprovação.

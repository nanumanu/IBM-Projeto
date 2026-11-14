# Conversa com o IBM Bob

Roteiro curto para usar o Bob de verdade no SafeOne, em uma sessão. São mensagens para colar
no chat do Bob, nesta ordem. Os detalhes de cada tarefa já estão em `BOB_TAREFAS.md`, e o Bob
lê esse arquivo sozinho.

## Antes de começar

- No terminal: `git checkout bob && git pull`.
- Abra a pasta raiz do repositório na IDE do Bob.
- **Use o agente do próprio Bob (os modos dele: Ask, Architect, Code), não o Claude Code
  conectado na IDE.** O que o Claude Code fizer conta como uso do Claude Code, mesmo dentro da
  IDE do Bob. Para a submissão dizer "o Bob fez", tem que ter sido o Bob.
- Salve as capturas em `docs/evidencias-bob/` como descrito em `BOB_TAREFAS.md`.

## 1. Perguntas (modo Ask) — uns 5 minutos

> Leia o README.md e o orchestrate/README.md. Explique em poucas linhas como o SafeOne detecta
> uma conta-laranja e em que ponto o analista humano precisa aprovar.

> Em orchestrate/safeone_tools.py, por que o score da ACC-900020 passa do limiar se ela é
> legítima? Quais sinais pesam mais nesse caso?

Captura: `t0-01-perguntas.png`, com as respostas do Bob.

## 2. Arquitetura (modo Architect) — Tarefa 1

> Leia o arquivo BOB_TAREFAS.md e execute a Tarefa 1 exatamente como o prompt dela descreve.
> Crie só o docs/arquitetura.md.

Confira o critério de pronto da Tarefa 1 e faça o commit:
`git add docs && git commit -m "Bob: tarefa 1 - documento de arquitetura"`

## 3. Nova ferramenta (modo Code) — Tarefa 3

> Leia o arquivo BOB_TAREFAS.md e execute a Tarefa 3 exatamente como o prompt dela descreve.
> No final, rode o comando de verificação que está no prompt e mostre a saída.

Commit: `Bob: tarefa 3 - ferramenta build_audit_record`

## 4. Testes (modo Code) — Tarefa 4

> Leia o arquivo BOB_TAREFAS.md e execute a Tarefa 4 exatamente como o prompt dela descreve.
> No final, rode os dois comandos de pytest e mostre as saídas.

Commit: `Bob: tarefa 4 - testes unitários das ferramentas`

## 5. Revisão de segurança (modo Ask ou Architect) — Tarefa 2

> Leia o arquivo BOB_TAREFAS.md e execute a Tarefa 2 exatamente como o prompt dela descreve.
> Não altere nenhum arquivo de código; crie só o docs/revisao-seguranca-bob.md.

Commit: `Bob: tarefa 2 - revisão de segurança`

## 6. Resumo da sessão (qualquer modo)

> Resuma, em uma lista, o que você fez nesta sessão: arquivos criados ou alterados, comandos
> que rodou e o resultado deles, e qualquer coisa que ficou pendente ou que você não conseguiu
> fazer.

Captura: `t9-01-resumo-bob.png`. Copie o resumo para a mensagem que avisa que o Bob terminou.

## Para terminar

```bash
git push origin bob
```

Se o tempo for curto, faça na ordem: 1, 2, 3 e 6. Já dá para a submissão dizer com verdade
que o Bob respondeu perguntas, gerou o documento de arquitetura e construiu uma ferramenta nova.

Se algo foi feito à mão ou pelo Claude Code no meio do caminho, faça um commit separado, sem o
prefixo `Bob:`, e avise. Na revisão, isso aparece separado do que o Bob fez.

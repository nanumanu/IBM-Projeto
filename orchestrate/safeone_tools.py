"""Ferramentas do SafeOne para o watsonx Orchestrate (Python tools).

Cada função marcada com @tool vira uma ferramenta que os agentes podem chamar.
Os dados são sintéticos e gerados de forma determinística a cada chamada, com
horários relativos ao momento atual. Como cada execução é isolada, nada fica gravado
entre chamadas: decisões e feedback mostram o efeito, mas não persistem.

Cenários plantados:
  ACC-900001  conta-laranja (deve abrir caso com score alto)
  ACC-900010  loja legítima com muitas origens (NÃO deve abrir caso)
  ACC-900020  república de estudantes (abre caso, mas é falso positivo)
"""
import random
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from ibm_watsonx_orchestrate.agent_builder.tools import tool

# ----------------------------------------------------------------- configuração
THRESHOLD = 60.0
WINDOW_HOURS = 2
WEIGHTS = {
    "network_fan_in": 35.0,
    "pass_through": 25.0,
    "new_account": 15.0,
    "disputes": 15.0,
    "inbound_spike": 10.0,
}
SIGNAL_LABELS = {
    "network_fan_in": "Padrão de rede (muitas instituições de origem)",
    "pass_through": "Repasse rápido do dinheiro",
    "new_account": "Conta recente",
    "disputes": "Contestações",
    "inbound_spike": "Entrada fora do padrão",
}
INSTITUTIONS = {
    "BCO01": "Banco Aurora", "BCO02": "Banco Horizonte", "BCO03": "Cooperativa Pampa",
    "BCO04": "Banco Atlântico", "BCO05": "Banco Serra Azul", "BCO06": "Nimbus Digital",
    "BCO07": "Banco Ipê", "BCO08": "Caixa Rio Claro", "BCO09": "Banco Litoral",
    "BCO10": "Pago Fácil IP", "BCO11": "Banco Cerrado", "BCO12": "Banco Guaíba",
    "BCO13": "Conta Já IP", "BCO14": "Banco Planalto",
}
FIRST = ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Heitor", "Isabela",
         "João", "Larissa", "Marcos", "Natália", "Otávio", "Paula", "Rafael", "Sofia", "Tiago"]
LAST = ["Silva", "Souza", "Oliveira", "Santos", "Lima", "Pereira", "Costa", "Rodrigues", "Almeida"]
DISPUTE_REASONS = ["Golpe do falso parente pelo WhatsApp", "Falsa central de atendimento",
                   "Compra em loja falsa na internet", "Falso funcionário pediu transferência"]


def _brl(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


# ----------------------------------------------------------------- dados sintéticos
def _build_world(seed: int = 42) -> dict:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
    codes = list(INSTITUTIONS)
    accounts: dict[str, dict] = {}
    txs: list[dict] = []
    disputes: list[dict] = []

    def acc(id_, inst, name, days, kind="PF"):
        accounts[id_] = {"id": id_, "institution": inst, "holder": name, "type": kind,
                         "opened_at": now - timedelta(days=days)}
        return id_

    def tx(src, dst, amount, minutes_ago, channel="PIX"):
        t = {"id": f"TX-{len(txs) + 1:06d}", "src": src, "dst": dst, "amount": round(amount, 2),
             "at": now - timedelta(minutes=minutes_ago), "channel": channel}
        txs.append(t)
        return t

    normal = [acc(f"ACC-{100000 + i}", codes[i % 14], f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                  rng.randint(120, 3000)) for i in range(320)]
    for _ in range(2600):
        a, b = rng.sample(normal, 2)
        tx(a, b, min(rng.lognormvariate(4.8, 1.0), 8000), rng.randint(1, 7 * 24 * 60))

    # cenário 1: rede de contas-laranja
    mule = acc("ACC-900001", "BCO06", "Renan Moura", 6)
    m2 = acc("ACC-900002", "BCO10", "Kelly Duarte", 11)
    m3 = acc("ACC-900003", "BCO13", "Jefferson Lins", 9)
    m4 = acc("ACC-900004", "BCO10", "Ricardo Paiva", 4)
    by_inst = defaultdict(list)
    for a in normal:
        by_inst[accounts[a]["institution"]].append(a)
    victims = [rng.choice(by_inst[c]) for c in codes]
    victims += rng.sample([a for a in normal if a not in victims], 2)
    victim_txs = [tx(v, mule, rng.uniform(800, 4500), rng.randint(40, 110)) for v in victims]
    inflow = sum(t["amount"] for t in victim_txs)
    tx(mule, m2, inflow * 0.45, 34)
    tx(mule, m3, inflow * 0.30, 28)
    tx(mule, m2, inflow * 0.15, 21)
    tx(m2, m4, inflow * 0.48, 15)

    # cenário 2: loja legítima
    shop = acc("ACC-900010", "BCO03", "Padaria Bom Grão Ltda", 1500, "PJ")
    for day in range(30):
        for _ in range(22):
            tx(rng.choice(normal), shop, rng.uniform(15, 180), day * 1440 + rng.randint(130, 900))
    for _ in range(25):
        tx(rng.choice(normal), shop, rng.uniform(15, 180), rng.randint(5, 115))

    # cenário 3: república (falso positivo)
    rep = acc("ACC-900020", "BCO12", "Mariana Kehl", 20)
    roommates = [rng.choice(by_inst[c]) for c in ["BCO01", "BCO02", "BCO05", "BCO07", "BCO09", "BCO14"]]
    for r in roommates:
        tx(r, rep, 720.0, rng.randint(50, 100))
    tx(rep, normal[7], 720.0 * 6 * 0.95, 20, "TED")

    for t in rng.sample(victim_txs, 4):
        disputes.append({"transaction_id": t["id"], "src": t["src"], "dst": t["dst"],
                         "amount": t["amount"], "reason": rng.choice(DISPUTE_REASONS),
                         "at": now - timedelta(minutes=rng.randint(5, 15))})
    return {"now": now, "accounts": accounts, "txs": txs, "disputes": disputes}


# ----------------------------------------------------------------- Sentinela
def _assess(w: dict, account_id: str) -> dict:
    now, a = w["now"], w["accounts"][account_id]
    start = now - timedelta(hours=WINDOW_HOURS)
    inbound = [t for t in w["txs"] if t["dst"] == account_id and start < t["at"] <= now]
    outflow = sum(t["amount"] for t in w["txs"] if t["src"] == account_id and start < t["at"] <= now)
    inflow = sum(t["amount"] for t in inbound)
    insts = {w["accounts"][t["src"]]["institution"] for t in inbound}
    hist = sum(t["amount"] for t in w["txs"]
               if t["dst"] == account_id and now - timedelta(days=30) < t["at"] <= start)
    age = (now - a["opened_at"]).days
    baseline = max(hist / max(1, min(30, age)) / (24 / WINDOW_HOURS), 300.0)
    n_disp = sum(1 for d in w["disputes"] if d["dst"] == account_id)
    ratio = outflow / inflow if inflow else 0.0
    spike = inflow / baseline

    signals = {
        "network_fan_in": (_clamp((len(insts) - 3) / 7),
                           f"Recebeu de {len(insts)} instituições diferentes nas últimas {WINDOW_HOURS}h "
                           f"({len(inbound)} transferências)."),
        "pass_through": (_clamp((ratio - 0.5) / 0.4) if inflow else 0.0,
                         f"Repassou {ratio:.0%} do que recebeu (entrou {_brl(inflow)}, saiu {_brl(outflow)})."),
        "new_account": (1.0 if age < 30 else 0.5 if age < 90 else 0.0, f"Conta aberta há {age} dias."),
        "disputes": (_clamp(n_disp / 3), f"{n_disp} transferência(s) recebida(s) contestada(s)."),
        "inbound_spike": (_clamp((spike - 3) / 7), f"Entrada {spike:.1f}x acima do normal da conta."),
    }
    score = 100 * sum(WEIGHTS[k] * v for k, (v, _) in signals.items()) / sum(WEIGHTS.values())
    return {
        "account_id": account_id,
        "score": round(score, 1),
        "threshold": THRESHOLD,
        "above_threshold": score >= THRESHOLD,
        "signals": [{"name": k, "label": SIGNAL_LABELS[k], "value": round(v, 2),
                     "weight": WEIGHTS[k], "evidence": e} for k, (v, e) in signals.items()],
        # só os sinais que de fato contribuíram para o score (value > 0)
        "active_signals": [f"{SIGNAL_LABELS[k]}: {e}" for k, (v, e) in signals.items() if v > 0],
    }


def _check_account(w: dict, account_id: str) -> None:
    if account_id not in w["accounts"]:
        raise ValueError(f"Conta {account_id} não encontrada.")


@tool
def scan_recent_activity() -> dict:
    """Varre as transferências recentes e lista as contas com padrão suspeito de fraude.

    Avalia todas as contas que receberam dinheiro nas últimas 2 horas e devolve as que
    passaram do limiar de risco, com o score e os sinais que explicam o motivo.

    Returns:
        dict: contas avaliadas e lista de casos suspeitos, do maior para o menor score.
    """
    w = _build_world()
    start = w["now"] - timedelta(hours=WINDOW_HOURS)
    recent = {t["dst"] for t in w["txs"] if t["at"] > start}
    results = [_assess(w, a) for a in sorted(recent)]
    hits = sorted((r for r in results if r["above_threshold"]), key=lambda r: -r["score"])
    return {
        "accounts_evaluated": len(results),
        "suspicious_cases": [
            {"case_id": f"CASO-{r['account_id'][4:]}", "account_id": r["account_id"], "score": r["score"],
             "main_signals": [s["evidence"] for s in sorted(r["signals"], key=lambda s: -s["value"])[:3]
                              if s["value"] > 0]}
            for r in hits
        ],
    }


@tool
def score_account(account_id: str) -> dict:
    """Calcula o score de risco (0 a 100) de uma conta e explica cada sinal.

    Args:
        account_id (str): identificador da conta, por exemplo ACC-900001.

    Returns:
        dict: score, limiar e a lista de sinais com intensidade, peso e evidência.
    """
    w = _build_world()
    _check_account(w, account_id)
    return _assess(w, account_id)


# ----------------------------------------------------------------- Investigador
def _network(w: dict, account_id: str, depth: int = 2) -> dict:
    since = w["now"] - timedelta(hours=24)
    txs = [t for t in w["txs"] if t["at"] > since]
    out_e, in_e = defaultdict(list), defaultdict(list)
    for t in txs:
        out_e[t["src"]].append(t)
        in_e[t["dst"]].append(t)
    dist, q = {account_id: 0}, deque([account_id])
    while q:
        n = q.popleft()
        if dist[n] >= depth:
            continue
        for nb in [t["dst"] for t in out_e[n]] + [t["src"] for t in in_e[n]]:
            if nb not in dist:
                dist[nb] = dist[n] + 1
                q.append(nb)
    accs = w["accounts"]
    inbound = [t for t in in_e[account_id]]
    outbound = defaultdict(float)
    for t in out_e[account_id]:
        outbound[t["dst"]] += t["amount"]
    total_in = sum(t["amount"] for t in inbound)
    total_out = sum(outbound.values())
    def _forwarded_to(src: str) -> list[dict]:
        # 2º salto: para quem cada destino repassou o dinheiro
        sums = defaultdict(float)
        for t in out_e[src]:
            sums[t["dst"]] += t["amount"]
        return [{"account_id": k, "institution": INSTITUTIONS[accs[k]["institution"]],
                 "amount": round(v, 2), "account_age_days": (w["now"] - accs[k]["opened_at"]).days}
                for k, v in sorted(sums.items(), key=lambda kv: -kv[1])]

    downstream = [
        {"account_id": d, "institution": INSTITUTIONS[accs[d]["institution"]],
         "received": round(v, 2), "account_age_days": (w["now"] - accs[d]["opened_at"]).days,
         "forwarded_onward": round(sum(t["amount"] for t in out_e[d]), 2),
         "forwarded_to": _forwarded_to(d)}
        for d, v in sorted(outbound.items(), key=lambda kv: -kv[1])
    ]
    # frases prontas do rastro, para o agente não inverter quem enviou e quem recebeu
    lines = []
    for d in downstream:
        line = f"{account_id} enviou {_brl(d['received'])} para {d['account_id']} ({d['institution']})"
        if d["forwarded_to"]:
            line += ", que repassou " + "; ".join(
                f"{_brl(x['amount'])} para {x['account_id']} ({x['institution']})" for x in d["forwarded_to"])
        else:
            line += ", que não repassou adiante"
        lines.append(line + ".")
    trail_summary = " ".join(lines) or f"{account_id} não enviou dinheiro nas últimas 24h."
    return {
        "accounts_in_network": len(dist),
        "institutions_in_network": len({accs[a]["institution"] for a in dist}),
        "source_institutions": len({accs[t["src"]]["institution"] for t in inbound}),
        "inbound_total": round(total_in, 2),
        "outbound_total": round(total_out, 2),
        "estimated_remaining": round(max(0.0, total_in - total_out), 2),
        "money_trail": downstream,
        "trail_summary": trail_summary,
    }


@tool
def investigate_account(account_id: str) -> dict:
    """Reúne o contexto de uma conta suspeita: cadastro, rede de transferências e contestações.

    Mostra de quantas instituições o dinheiro veio, para onde ele foi depois (rastro do
    dinheiro) e quais transferências recebidas foram contestadas por clientes.

    Args:
        account_id (str): identificador da conta, por exemplo ACC-900001.

    Returns:
        dict: dados da conta, resumo da rede em 24h, rastro do dinheiro e contestações.
    """
    w = _build_world()
    _check_account(w, account_id)
    a = w["accounts"][account_id]
    return {
        "account": {"account_id": account_id, "holder": a["holder"], "holder_type": a["type"],
                    "institution": INSTITUTIONS[a["institution"]],
                    "account_age_days": (w["now"] - a["opened_at"]).days},
        "network": _network(w, account_id),
        "disputes": [{"transaction_id": d["transaction_id"], "amount": d["amount"], "reason": d["reason"]}
                     for d in w["disputes"] if d["dst"] == account_id],
        "disputes_total": round(sum(d["amount"] for d in w["disputes"] if d["dst"] == account_id), 2),
    }


# ----------------------------------------------------------------- Decisão
def _dossier(w: dict, account_id: str) -> dict:
    risk = _assess(w, account_id)
    net = _network(w, account_id)
    disp = [d for d in w["disputes"] if d["dst"] == account_id]
    score = risk["score"]
    actions = []
    if score >= 85:
        rec = "bloquear_e_recuperar"
        actions.append({"action_id": "A1", "type": "bloquear_conta", "target": account_id})
        for i, d in enumerate(x for x in net["money_trail"] if x["account_age_days"] < 30):
            actions.append({"action_id": f"A{len(actions) + 1}", "type": "bloquear_conta", "target": d["account_id"],
                            "reason": "destino do repasse, conta recente"})
        for d in disp:
            actions.append({"action_id": f"A{len(actions) + 1}", "type": "solicitar_devolucao",
                            "target": d["transaction_id"], "amount": d["amount"]})
        why = ("Score muito alto com padrão típico de conta de passagem. Bloquear a conta e os destinos "
               "recentes do repasse interrompe a dispersão; pedir devolução das transferências contestadas "
               "protege as vítimas já identificadas.")
    elif score >= THRESHOLD:
        rec = "bloqueio_cautelar_e_revisao"
        actions.append({"action_id": "A1", "type": "bloquear_conta", "target": account_id})
        why = ("Score acima do limiar, mas sem a combinação completa de sinais de conta-laranja. Bloqueio "
               "cautelar enquanto o analista confirma com a instituição de origem.")
    else:
        rec = "monitorar"
        why = "Sinais fracos. Manter em observação, sem ação sobre a conta."
    if net["estimated_remaining"] > 0 and score >= THRESHOLD:
        why += f" Ainda há cerca de {_brl(net['estimated_remaining'])} na conta que podem ser preservados."
    return {"risk": risk, "network": net, "disputes": disp, "recommendation": rec,
            "justification": why, "proposed_actions": actions}


@tool
def build_case_dossier(account_id: str) -> dict:
    """Monta o dossiê de um caso: evidências, recomendação, justificativa e ações propostas.

    As ações ficam apenas propostas. Nenhuma é executada sem a aprovação explícita de um
    analista humano.

    Args:
        account_id (str): conta investigada, por exemplo ACC-900001.

    Returns:
        dict: recomendação, justificativa, evidências, rastro do dinheiro e ações propostas.
    """
    w = _build_world()
    _check_account(w, account_id)
    d = _dossier(w, account_id)
    evidence = [{"label": s["label"], "strength": s["value"], "evidence": s["evidence"]}
                for s in sorted(d["risk"]["signals"], key=lambda s: -s["value"]) if s["value"] > 0]
    # texto pronto para exibir: o agente copia este bloco antes de pedir a decisão
    disputes_total = sum(x["amount"] for x in d["disputes"])
    lines = [f"Dossiê do caso CASO-{account_id[4:]} (conta {account_id})",
             f"Score de risco: {d['risk']['score']:g}/100".replace(".", ","),
             f"Recomendação: {d['recommendation']}",
             f"Justificativa: {d['justification']}",
             "Evidências:"]
    lines += [f"- {e['label']}: {e['evidence']}" for e in evidence]
    lines.append(f"Rastro do dinheiro: {d['network']['trail_summary']}")
    if d["disputes"]:
        lines.append(f"Contestações: {len(d['disputes'])}, total de {_brl(disputes_total)}.")
    if d["proposed_actions"]:
        lines.append("Ações propostas (só serão executadas com a aprovação do analista):")
        for a in d["proposed_actions"]:
            extra = a.get("reason") or (_brl(a["amount"]) if "amount" in a else "")
            lines.append(f"- {a['action_id']} {a['type']} {a['target']}" + (f" ({extra})" if extra else ""))
    else:
        lines.append("Nenhuma ação proposta.")
    return {
        "case_id": f"CASO-{account_id[4:]}",
        "account_id": account_id,
        "risk_score": d["risk"]["score"],
        "recommendation": d["recommendation"],
        "justification": d["justification"],
        "evidence": evidence,
        "network_summary": {k: v for k, v in d["network"].items() if k != "money_trail"},
        "money_trail": d["network"]["money_trail"],
        "disputes": [{"transaction_id": x["transaction_id"], "amount": x["amount"], "reason": x["reason"]}
                     for x in d["disputes"]],
        "disputes_total": round(sum(x["amount"] for x in d["disputes"]), 2),
        "proposed_actions": d["proposed_actions"],
        "display_text": "\n".join(lines),
        "status": "aguardando_aprovacao_do_analista",
        "checklist": [
            "Confirmar com ao menos uma instituição de origem se houve relato de golpe.",
            "Verificar se a conta tem justificativa comercial para receber de muitas origens.",
            "Conferir se os destinos do repasse também são contas recentes.",
        ],
    }


@tool
def record_analyst_decision(account_id: str, approved: bool, analyst_name: str = "") -> dict:
    """Registra a decisão do analista humano sobre as ações propostas no dossiê.

    Use SOMENTE depois que o analista disser explicitamente na conversa que aprova ou
    rejeita. Nunca chame esta ferramenta por iniciativa própria.

    Args:
        account_id (str): conta do caso, por exemplo ACC-900001.
        approved (bool): True se o analista aprovou as ações, False se rejeitou.
        analyst_name (str): nome do analista que decidiu, se já foi dito na conversa.
            Sem nome, a decisão fica registrada como "analista (nome não informado)".

    Returns:
        dict: status do caso e efeito de cada ação (executada ou descartada).
    """
    w = _build_world()
    _check_account(w, account_id)
    d = _dossier(w, account_id)
    effects = []
    for a in d["proposed_actions"]:
        if not approved:
            effects.append({**a, "status": "descartada"})
        elif a["type"] == "bloquear_conta":
            effects.append({**a, "status": "executada",
                            "effect": "Conta bloqueada; novas transferências de ou para ela ficam retidas."})
        else:
            effects.append({**a, "status": "executada",
                            "effect": f"Devolução de {_brl(a['amount'])} solicitada à instituição de destino."})
    returned = sum(a.get("amount", 0) for a in effects if a["status"] == "executada")
    decided_by = analyst_name.strip() or "analista (nome não informado)"
    # texto pronto para exibir: o agente copia este bloco em vez de resumir as ações
    lines = [f"Decisão registrada no caso CASO-{account_id[4:]}: "
             f"{'aprovado' if approved else 'rejeitado'} por {decided_by}."]
    lines += [f"- {a['action_id']} ({a['type']}, {a['target']}): " + (a["effect"] if a["status"] == "executada" else "descartada")
              for a in effects]
    if not effects:
        lines.append("Não havia ações propostas para este caso.")
    if approved and returned:
        lines.append(f"Total de devolução solicitado: {_brl(returned)}.")
    return {
        "case_id": f"CASO-{account_id[4:]}",
        "status": "aprovado" if approved else "rejeitado",
        "decided_by": decided_by,
        "actions": effects,
        "amount_requested_back": round(returned, 2),
        "display_text": "\n".join(lines),
        "note": "Simulação da POC: o efeito é mostrado, mas não fica gravado entre conversas.",
    }


# ----------------------------------------------------------------- Comunicação
@tool
def draft_notifications(account_id: str, case_approved: bool) -> dict:
    """Redige os avisos ao titular da conta e às vítimas que contestaram transferências.

    Só gera mensagens quando o caso foi aprovado pelo analista.

    Args:
        account_id (str): conta do caso, por exemplo ACC-900001.
        case_approved (bool): True se o analista já aprovou o caso.

    Returns:
        dict: mensagens para o titular e para cada vítima, em linguagem simples.
    """
    if not case_approved:
        return {"messages": [], "error": "Avisos só podem ser enviados depois da aprovação do analista."}
    w = _build_world()
    _check_account(w, account_id)
    if not _assess(w, account_id)["above_threshold"]:
        return {"messages": [], "error": f"A conta {account_id} não tem caso aberto; nenhum aviso foi gerado."}
    tip = ("Lembre-se: a sua instituição nunca pede senha, código de verificação ou transferência "
           "para 'conta de segurança'.")
    msgs = [{"audience": "titular", "account_id": account_id, "message": (
        "Sua conta foi bloqueada temporariamente para uma verificação de segurança. Se você reconhece as "
        "movimentações recentes, procure sua agência ou o canal oficial do seu banco com um documento.")}]
    for d in w["disputes"]:
        if d["dst"] == account_id:
            msgs.append({"audience": "vitima", "account_id": d["src"], "message": (
                f"Recebemos sua contestação da transferência de {_brl(d['amount'])}. A devolução foi "
                f"solicitada e você será avisado assim que o valor voltar. {tip}")})
    # texto pronto para exibir: o agente copia este bloco em vez de remontar as mensagens
    display = "\n\n".join(
        f"Para: {'Titular' if m['audience'] == 'titular' else 'Vítima'} (conta {m['account_id']})\n{m['message']}"
        for m in msgs
    )
    return {"messages": msgs, "display_text": display}


# ----------------------------------------------------------------- Aprendizado
@tool
def record_feedback(account_id: str, was_fraud: bool) -> dict:
    """Registra se o caso era fraude ou falso positivo e mostra como os pesos dos sinais mudam.

    Os sinais que pesaram no caso sobem 10% se era fraude e descem 10% se era falso positivo.

    Args:
        account_id (str): conta do caso, por exemplo ACC-900020.
        was_fraud (bool): True se o analista confirmou fraude, False se era legítimo.

    Returns:
        dict: peso antes e depois de cada sinal ajustado e o novo score da conta.
    """
    w = _build_world()
    _check_account(w, account_id)
    risk = _assess(w, account_id)
    factor = 1.1 if was_fraud else 0.9
    new_w = dict(WEIGHTS)
    changes = {}
    for s in risk["signals"]:
        if s["value"] >= 0.5:
            new_w[s["name"]] = round(max(5.0, min(60.0, WEIGHTS[s["name"]] * factor)), 2)
            changes[s["label"]] = {"before": WEIGHTS[s["name"]], "after": new_w[s["name"]]}
    new_score = 100 * sum(new_w[s["name"]] * s["value"] for s in risk["signals"]) / sum(new_w.values())
    return {
        "case_id": f"CASO-{account_id[4:]}",
        "label": "fraude" if was_fraud else "legitimo",
        "weight_changes": changes,
        "score_before": risk["score"],
        "score_after_learning": round(new_score, 1),
        "note": "Simulação da POC: os novos pesos valem para esta análise e não ficam gravados.",
    }

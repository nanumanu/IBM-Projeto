"""Testes unitários das ferramentas de orchestrate/safeone_tools.py.

Rodam localmente, sem conexão com o watsonx Orchestrate. No ADK 2.19.1, uma função decorada
com @tool, chamada direto no Python, devolve um ToolResponse com o dict da função em
.content; os erros (conta inexistente) não são embrulhados e sobem como ValueError.

Os horários não são comparados com valores exatos, porque os dados são relativos ao momento
em que cada chamada roda.
"""
import re
from datetime import datetime, timedelta

import pytest

import safeone_tools as t

MULE, SHOP, REP = "ACC-900001", "ACC-900010", "ACC-900020"
SEM_NOME = "analista (nome não informado)"
# R$ 1.234,56: milhar com ponto, centavos com vírgula
DINHEIRO = re.compile(r"R\$ \d{1,3}(?:\.\d{3})*,\d{2}(?!\d)")


def chamar(ferramenta, *args, **kwargs) -> dict:
    """Chama a ferramenta e devolve o dict que a função retornou (ToolResponse.content)."""
    return ferramenta(*args, **kwargs).content


# --------------------------------------------------------------- 1. ACC-900001, conta-laranja
def test_mule_score_100_acima_do_limiar():
    r = chamar(t.score_account, MULE)
    assert r["score"] == 100
    assert r["threshold"] == t.THRESHOLD
    assert r["above_threshold"] is True


def test_mule_dossie_recomenda_bloquear_e_recuperar_com_a1_a_a7():
    d = chamar(t.build_case_dossier, MULE)
    assert d["case_id"] == "CASO-900001"
    assert d["recommendation"] == "bloquear_e_recuperar"
    assert [a["action_id"] for a in d["proposed_actions"]] == [f"A{i}" for i in range(1, 8)]
    assert d["status"] == "aguardando_aprovacao_do_analista"


def test_mule_rastro_vai_para_900002_e_depois_900004():
    r = chamar(t.investigate_account, MULE)
    trail = {d["account_id"]: d for d in r["network"]["money_trail"]}
    assert "ACC-900002" in trail
    assert [x["account_id"] for x in trail["ACC-900002"]["forwarded_to"]] == ["ACC-900004"]
    # no texto pronto a ordem também é 900001 -> 900002 -> 900004
    texto = r["display_text"]
    assert texto.index("ACC-900002") < texto.index("ACC-900004")


def test_mule_aprovacao_executa_as_7_acoes():
    r = chamar(t.record_analyst_decision, MULE, True, "Manuela")
    assert r["status"] == "aprovado"
    assert r["decided_by"] == "Manuela"
    assert len(r["actions"]) == 7
    assert all(a["status"] == "executada" for a in r["actions"])
    assert r["amount_requested_back"] > 0


def test_mule_avisos_1_titular_e_4_vitimas():
    r = chamar(t.draft_notifications, MULE, True)
    publicos = [m["audience"] for m in r["messages"]]
    assert publicos.count("titular") == 1
    assert publicos.count("vitima") == 4
    assert "error" not in r


# --------------------------------------------------------------- 2. ACC-900010, loja legítima
def test_loja_score_42_abaixo_do_limiar():
    r = chamar(t.score_account, SHOP)
    assert r["score"] == 42
    assert r["above_threshold"] is False


def test_loja_recomendacao_monitorar_sem_acoes():
    d = chamar(t.build_case_dossier, SHOP)
    assert d["recommendation"] == "monitorar"
    assert d["proposed_actions"] == []


def test_loja_avisos_devolvem_erro_sem_caso_aberto():
    r = chamar(t.draft_notifications, SHOP, True)
    assert r["messages"] == []
    assert "não tem caso aberto" in r["error"]


# --------------------------------------------------------------- 3. ACC-900020, falso positivo
def test_republica_score_65_acima_do_limiar():
    r = chamar(t.score_account, REP)
    assert r["score"] == 65
    assert r["above_threshold"] is True


def test_republica_rejeicao_descarta_todas_as_acoes():
    r = chamar(t.record_analyst_decision, REP, False, "Manuela")
    assert r["status"] == "rejeitado"
    assert r["actions"], "a república deveria ter ao menos uma ação proposta"
    assert all(a["status"] == "descartada" for a in r["actions"])
    assert r["amount_requested_back"] == 0


def test_republica_feedback_leva_score_de_65_para_63_2():
    r = chamar(t.record_feedback, REP, False)
    assert r["label"] == "legitimo"
    assert r["score_before"] == 65
    assert r["score_after_learning"] == 63.2
    assert "65 antes, 63,2 depois" in r["display_text"]
    assert "63.2" not in r["display_text"]


# --------------------------------------------------------------- 4. varredura
def test_varredura_mule_primeiro_republica_presente_loja_ausente():
    r = chamar(t.scan_recent_activity)
    contas = [c["account_id"] for c in r["suspicious_cases"]]
    assert contas[0] == MULE
    assert REP in contas
    assert SHOP not in contas
    scores = [c["score"] for c in r["suspicious_cases"]]
    assert scores == sorted(scores, reverse=True)


# --------------------------------------------------------------- 5. proteções
def test_avisos_sem_aprovacao_nao_geram_mensagens():
    r = chamar(t.draft_notifications, MULE, False)
    assert r["messages"] == []
    assert "aprovação do analista" in r["error"]
    assert "display_text" not in r


@pytest.mark.parametrize("chamada", [
    lambda: t.score_account("ACC-123"),
    lambda: t.investigate_account("ACC-123"),
    lambda: t.build_case_dossier("ACC-123"),
    lambda: t.record_analyst_decision("ACC-123", True, "Manuela"),
    lambda: t.record_feedback("ACC-123", False),
    lambda: t.build_audit_record("ACC-123", True, "Manuela"),
], ids=["score_account", "investigate_account", "build_case_dossier", "record_analyst_decision",
        "record_feedback", "build_audit_record"])
def test_conta_inexistente_levanta_value_error(chamada):
    with pytest.raises(ValueError, match="ACC-123 não encontrada"):
        chamada()


# --------------------------------------------------------------- 6. build_audit_record
def test_auditoria_mule_aprovado():
    r = chamar(t.build_audit_record, MULE, True, "Manuela")
    assert r["case_id"] == "CASO-900001"
    assert r["account_id"] == MULE
    assert r["decision"] == "aprovado"
    assert r["decided_by"] == "Manuela"
    assert len(r["actions"]) == 7
    assert all(a["status"] == "executada" for a in r["actions"])
    assert r["rules_version"] == t.RULES_VERSION
    assert r["signal_weights"] == t.WEIGHTS
    assert r["score"] == 100 and r["threshold"] == t.THRESHOLD
    assert r["display_text"].startswith("Registro de auditoria do caso CASO-900001")
    assert "note" in r


def test_auditoria_data_em_iso_8601_utc():
    r = chamar(t.build_audit_record, MULE, True, "Manuela")
    quando = datetime.fromisoformat(r["decided_at"])  # falha se não for ISO 8601
    assert quando.utcoffset() == timedelta(0)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", r["decided_at"])


def test_auditoria_bate_com_a_decisao_registrada():
    auditoria = chamar(t.build_audit_record, MULE, True, "Manuela")
    decisao = chamar(t.record_analyst_decision, MULE, True, "Manuela")
    assert auditoria["actions"] == decisao["actions"]
    assert auditoria["amount_requested_back"] == decisao["amount_requested_back"]


def test_auditoria_so_traz_evidencias_de_sinais_ativos():
    r = chamar(t.build_audit_record, REP, False, "Manuela")
    ativos = [s["label"] for s in chamar(t.score_account, REP)["signals"] if s["value"] > 0]
    assert [e["label"] for e in r["evidence"]] == ativos
    assert "Contestações" not in ativos  # a república não tem contestação


def test_auditoria_republica_rejeitado_descarta_tudo():
    r = chamar(t.build_audit_record, REP, False, "Manuela")
    assert r["decision"] == "rejeitado"
    assert r["actions"]
    assert all(a["status"] == "descartada" for a in r["actions"])
    assert r["amount_requested_back"] == 0


def test_auditoria_loja_sem_caso_aberto_devolve_erro():
    r = chamar(t.build_audit_record, SHOP, True, "Manuela")
    assert "não tem caso aberto" in r["error"]
    assert "display_text" not in r and "case_id" not in r


@pytest.mark.parametrize("nome", ["", "   "])
def test_auditoria_sem_nome_usa_texto_padrao(nome):
    r = chamar(t.build_audit_record, MULE, True, nome)
    assert r["decided_by"] == SEM_NOME
    assert chamar(t.record_analyst_decision, MULE, True, nome)["decided_by"] == SEM_NOME


# --------------------------------------------------------------- 7. determinismo
@pytest.mark.parametrize("conta", [MULE, SHOP, REP])
def test_duas_chamadas_dao_o_mesmo_score_e_as_mesmas_acoes(conta):
    assert chamar(t.score_account, conta)["score"] == chamar(t.score_account, conta)["score"]
    a = chamar(t.build_case_dossier, conta)["proposed_actions"]
    b = chamar(t.build_case_dossier, conta)["proposed_actions"]
    assert a == b


# --------------------------------------------------------------- 8. formato
def _textos_prontos() -> dict[str, str]:
    textos = {}
    for conta in (MULE, SHOP, REP):
        textos[f"score_account {conta}"] = chamar(t.score_account, conta)["display_text"]
        textos[f"investigate_account {conta}"] = chamar(t.investigate_account, conta)["display_text"]
        textos[f"build_case_dossier {conta}"] = chamar(t.build_case_dossier, conta)["display_text"]
        textos[f"record_analyst_decision {conta}"] = chamar(
            t.record_analyst_decision, conta, True, "Manuela")["display_text"]
        textos[f"record_feedback {conta}"] = chamar(t.record_feedback, conta, True)["display_text"]
    for conta in (MULE, REP):  # só contas com caso aberto têm avisos e registro de auditoria
        textos[f"draft_notifications {conta}"] = chamar(t.draft_notifications, conta, True)["display_text"]
        textos[f"build_audit_record {conta}"] = chamar(
            t.build_audit_record, conta, True, "Manuela")["display_text"]
    return textos


def test_todo_display_text_e_str_nao_vazia():
    for origem, texto in _textos_prontos().items():
        assert isinstance(texto, str) and texto.strip(), origem


def test_valores_em_dinheiro_usam_o_formato_brasileiro():
    vistos = 0
    for origem, texto in _textos_prontos().items():
        total = texto.count("R$")
        assert len(DINHEIRO.findall(texto)) == total, f"valor fora do formato R$ 1.234,56 em {origem}"
        vistos += total
    assert vistos > 0


def test_brl_formata_milhar_e_centavos():
    assert t._brl(1234.56) == "R$ 1.234,56"
    assert t._brl(0) == "R$ 0,00"
    assert t._brl(1234567.8) == "R$ 1.234.567,80"

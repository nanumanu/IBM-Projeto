from tests.conftest import AGENT, ANALYST

MULE, SHOP, REP = "ACC-900001", "ACC-900010", "ACC-900020"


def _case_of(client, account_id):
    cases = client.get("/cases", headers=AGENT).json()
    return next(c for c in cases if c["account_id"] == account_id)


def test_requires_api_key(client):
    assert client.get("/cases").status_code == 401
    assert client.get("/cases", headers={"X-API-Key": "errada"}).status_code == 401


def test_seed_opens_expected_cases(client):
    accounts = {c["account_id"] for c in client.get("/cases", headers=AGENT).json()}
    assert MULE in accounts and REP in accounts
    assert SHOP not in accounts  # um sinal sozinho não abre caso


def test_network_signal_explained(client):
    risk = client.get(f"/accounts/{MULE}/risk", headers=AGENT).json()
    fan_in = next(s for s in risk["signals"] if s["name"] == "network_fan_in")
    assert risk["score"] >= 85 and fan_in["value"] == 1.0
    assert "14 instituições" in fan_in["evidence"]


def test_network_shows_money_trail(client):
    net = client.get(f"/accounts/{MULE}/network", headers=AGENT).json()
    assert net["summary"]["source_institutions"] == 14
    downstream = {d["account_id"] for d in net["downstream"]}
    assert downstream == {"ACC-900002", "ACC-900003"}
    assert any(n["account_id"] == "ACC-900004" for n in net["nodes"])  # 2º salto


def test_full_fraud_flow(client):
    case = _case_of(client, MULE)

    dossier = client.post(f"/cases/{case['id']}/dossier", headers=AGENT).json()
    assert dossier["recommendation"] == "block_and_recover"
    assert dossier["evidence"] and dossier["narrative"]

    detail = client.get(f"/cases/{case['id']}", headers=AGENT).json()
    assert detail["status"] == "awaiting_approval"
    assert all(a["status"] == "proposed" for a in detail["actions"])
    types = [a["type"] for a in detail["actions"]]
    assert types.count("request_return") == 4

    # agente NÃO pode decidir
    r = client.post(f"/cases/{case['id']}/decision", headers=AGENT,
                    json={"decision": "approve", "analyst": "bot"})
    assert r.status_code == 403
    assert client.get(f"/accounts/{MULE}", headers=AGENT).json()["status"] == "active"

    # comunicação antes da aprovação é bloqueada
    assert client.post(f"/cases/{case['id']}/notifications", headers=AGENT).status_code == 409

    r = client.post(f"/cases/{case['id']}/decision", headers=ANALYST,
                    json={"decision": "approve", "analyst": "manu", "note": "confirmado com BCO01"})
    assert r.status_code == 200
    assert all(a["status"] == "executed" for a in r.json()["actions"])
    assert client.get(f"/accounts/{MULE}", headers=AGENT).json()["status"] == "blocked"

    # depois do bloqueio, nova saída da conta fica retida
    r = client.post("/transactions", headers=AGENT,
                    json={"source_account_id": MULE, "dest_account_id": "ACC-100001", "amount": 500})
    assert r.json()["held"] is True

    notes = client.post(f"/cases/{case['id']}/notifications", headers=AGENT).json()
    audiences = [n["audience"] for n in notes]
    assert audiences.count("holder") == 1 and audiences.count("victim") == 4
    assert client.post(f"/cases/{case['id']}/notifications", headers=AGENT).json() == []  # sem repetir

    fb = client.post(f"/cases/{case['id']}/feedback", headers=ANALYST,
                     json={"label": "fraud", "analyst": "manu"}).json()
    assert fb["weight_changes"]["network_fan_in"]["after"] > fb["weight_changes"]["network_fan_in"]["before"]

    m = client.get("/metrics", headers=AGENT).json()
    assert m["amount_returned"] > 0 and m["precision"] == 1.0


def test_false_positive_lowers_weights(client):
    case = _case_of(client, REP)
    client.post(f"/cases/{case['id']}/dossier", headers=AGENT)
    r = client.post(f"/cases/{case['id']}/decision", headers=ANALYST,
                    json={"decision": "reject", "analyst": "manu", "note": "aluguel dividido"})
    assert r.json()["status"] == "rejected"
    assert client.get(f"/accounts/{REP}", headers=AGENT).json()["status"] == "active"

    fb = client.post(f"/cases/{case['id']}/feedback", headers=ANALYST,
                     json={"label": "legit", "analyst": "manu"}).json()
    assert "network_fan_in" not in fb["weight_changes"]  # sinal fraco não é ajustado
    pt = fb["weight_changes"]["pass_through"]
    assert pt["after"] < pt["before"]
    assert client.get(f"/accounts/{REP}/risk", headers=AGENT).json()["score"] < 65


def test_ingestion_opens_case_in_real_time(client):
    # nova conta-laranja recebendo de várias instituições, transferência a transferência
    from app.db import SessionLocal
    from app.models import Account, utcnow
    from datetime import timedelta

    with SessionLocal() as db:
        db.add(Account(id="ACC-NEW", institution_code="BCO06", holder_name="Teste",
                       document_masked="***", opened_at=utcnow() - timedelta(days=2)))
        db.commit()

    sources = [f"ACC-{100000 + i}" for i in range(14)]  # 14 instituições diferentes
    opened = None
    for s in sources:
        r = client.post("/transactions", headers=AGENT,
                        json={"source_account_id": s, "dest_account_id": "ACC-NEW", "amount": 2000}).json()
        if r["case_opened"]:
            opened = r
            break
    assert opened is not None and opened["dest_risk_score"] >= 60


def test_analyst_route_without_key_is_401(client):
    assert client.post("/admin/reset-demo").status_code == 401
    assert client.post("/admin/reset-demo", headers=AGENT).status_code == 403


def test_network_of_unknown_account_is_404(client):
    assert client.get("/accounts/NAO-EXISTE/network", headers=AGENT).status_code == 404


def test_same_transaction_cannot_be_disputed_twice(client):
    tx = client.get("/transactions", params={"account_id": REP}, headers=AGENT).json()[0]
    body = {"transaction_id": tx["id"], "reason": "golpe"}
    assert client.post("/disputes", headers=AGENT, json=body).status_code == 201
    assert client.post("/disputes", headers=AGENT, json=body).status_code == 409


def test_holder_not_told_blocked_on_partial_approval(client):
    case = _case_of(client, MULE)
    client.post(f"/cases/{case['id']}/dossier", headers=AGENT)
    actions = client.get(f"/cases/{case['id']}", headers=AGENT).json()["actions"]
    returns = [a["id"] for a in actions if a["type"] == "request_return"]
    client.post(f"/cases/{case['id']}/decision", headers=ANALYST,
                json={"decision": "approve", "analyst": "manu", "action_ids": returns})
    assert client.get(f"/accounts/{MULE}", headers=AGENT).json()["status"] == "active"
    notes = client.post(f"/cases/{case['id']}/notifications", headers=AGENT).json()
    holder = next(n for n in notes if n["audience"] == "holder")
    assert "bloqueada" not in holder["message"]


def test_false_positive_not_reopened_by_next_scan(client):
    case = _case_of(client, REP)
    client.post(f"/cases/{case['id']}/dossier", headers=AGENT)
    client.post(f"/cases/{case['id']}/decision", headers=ANALYST,
                json={"decision": "reject", "analyst": "manu"})
    client.post(f"/cases/{case['id']}/feedback", headers=ANALYST, json={"label": "legit", "analyst": "manu"})
    client.post("/monitoring/scan", headers=AGENT)
    open_for_rep = [c for c in client.get("/cases", headers=AGENT).json()
                    if c["account_id"] == REP and c["status"] != "closed"]
    assert open_for_rep == []


def test_cannot_decide_without_dossier(client):
    case = _case_of(client, MULE)
    r = client.post(f"/cases/{case['id']}/decision", headers=ANALYST,
                    json={"decision": "approve", "analyst": "manu"})
    assert r.status_code == 409

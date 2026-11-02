"""Dados sintéticos para a demo. Determinísticos (semente fixa) e relativos ao horário atual.

Cenários plantados (IDs fixos para facilitar a apresentação):
  ACC-900001  Conta-laranja: aberta há 6 dias, recebe de 14 instituições em ~1h, repassa 90%
              para ACC-900002 e ACC-900003, que repassam adiante (ACC-900004). 4 contestações.
  ACC-900010  Loja antiga que recebe de muitas instituições todo dia. Padrão de rede alto,
              mas sem outros sinais: NÃO deve abrir caso (mostra que um sinal sozinho não basta).
  ACC-900020  República de estudantes: conta nova que recebe o aluguel de 6 moradores e paga o
              proprietário. Abre caso, mas é legítimo: serve para demonstrar o falso positivo
              e o ajuste de pesos pelo Aprendizado.
"""
import random
from datetime import timedelta

from sqlalchemy.orm import Session

from app.db import Base
from app.models import Account, Dispute, Institution, Transaction, utcnow
from app.services import scoring

INSTITUTIONS = [
    ("BCO01", "Banco Aurora"), ("BCO02", "Banco Horizonte"), ("BCO03", "Cooperativa Pampa"),
    ("BCO04", "Banco Atlântico"), ("BCO05", "Banco Serra Azul"), ("BCO06", "Nimbus Digital"),
    ("BCO07", "Banco Ipê"), ("BCO08", "Caixa Rio Claro"), ("BCO09", "Banco Litoral"),
    ("BCO10", "Pago Fácil IP"), ("BCO11", "Banco Cerrado"), ("BCO12", "Banco Guaíba"),
    ("BCO13", "Conta Já IP"), ("BCO14", "Banco Planalto"),
]
FIRST = ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Heitor", "Isabela",
         "João", "Larissa", "Marcos", "Natália", "Otávio", "Paula", "Rafael", "Sofia", "Tiago",
         "Vitória", "William", "Yasmin", "Lucas", "Beatriz", "Rodrigo", "Camila", "Pedro"]
LAST = ["Silva", "Souza", "Oliveira", "Santos", "Lima", "Pereira", "Costa", "Rodrigues", "Almeida",
        "Nascimento", "Carvalho", "Ribeiro", "Gomes", "Martins", "Rocha", "Barbosa", "Teixeira"]
DISPUTE_REASONS = ["Golpe do falso parente pelo WhatsApp", "Falsa central de atendimento",
                   "Compra em loja falsa na internet", "Falso funcionário pediu transferência"]


def _doc(rng: random.Random, pj: bool = False) -> str:
    if pj:
        return f"**.{rng.randint(100, 999)}.{rng.randint(100, 999)}/0001-**"
    return f"***.{rng.randint(100, 999)}.{rng.randint(100, 999)}-**"


def reset_and_seed(db: Session, seed: int = 42) -> dict:
    Base.metadata.drop_all(db.get_bind())
    Base.metadata.create_all(db.get_bind())
    rng = random.Random(seed)
    now = utcnow()

    db.add_all(Institution(code=c, name=n) for c, n in INSTITUTIONS)
    codes = [c for c, _ in INSTITUTIONS]

    # --------------------------------------------------- contas comuns
    normal: list[Account] = []
    for i in range(320):
        normal.append(Account(
            id=f"ACC-{100000 + i}",
            institution_code=codes[i % len(codes)],
            holder_name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            document_masked=_doc(rng),
            opened_at=now - timedelta(days=rng.randint(120, 3000)),
        ))
    db.add_all(normal)

    txs: list[Transaction] = []

    def tx(src, dst, amount, at, channel="PIX"):
        t = Transaction(source_account_id=src.id, dest_account_id=dst.id, amount=round(amount, 2),
                        created_at=at, channel=channel)
        txs.append(t)
        return t

    # movimento normal: 7 dias, valores típicos de Pix do dia a dia
    for _ in range(2600):
        a, b = rng.sample(normal, 2)
        amount = min(rng.lognormvariate(4.8, 1.0), 8000)
        tx(a, b, amount, now - timedelta(minutes=rng.randint(1, 7 * 24 * 60)),
           "TED" if amount > 3000 and rng.random() < 0.4 else "PIX")

    # --------------------------------------------------- cenário 1: rede de contas-laranja
    def new_acc(id_, inst, name, days):
        acc = Account(id=id_, institution_code=inst, holder_name=name, document_masked=_doc(rng),
                      opened_at=now - timedelta(days=days))
        db.add(acc)
        return acc

    mule = new_acc("ACC-900001", "BCO06", "Renan Moura", 6)
    mule2 = new_acc("ACC-900002", "BCO10", "Kelly Duarte", 11)
    mule3 = new_acc("ACC-900003", "BCO13", "Jefferson Lins", 9)
    mule4 = new_acc("ACC-900004", "BCO10", "Ricardo Paiva", 4)

    by_inst: dict[str, list[Account]] = {}
    for acc in normal:
        by_inst.setdefault(acc.institution_code, []).append(acc)
    victims = [rng.choice(by_inst[c]) for c in codes]                 # 14 instituições
    victims += rng.sample([a for a in normal if a not in victims], 2)  # 16 vítimas
    victim_txs = []
    for v in victims:
        at = now - timedelta(minutes=rng.randint(40, 110))
        victim_txs.append(tx(v, mule, rng.uniform(800, 4500), at))
    inflow = sum(t.amount for t in victim_txs)

    tx(mule, mule2, inflow * 0.45, now - timedelta(minutes=34))
    tx(mule, mule3, inflow * 0.30, now - timedelta(minutes=28))
    tx(mule, mule2, inflow * 0.15, now - timedelta(minutes=21))
    tx(mule2, mule4, inflow * 0.48, now - timedelta(minutes=15))

    # --------------------------------------------------- cenário 2: loja legítima
    shop = Account(id="ACC-900010", institution_code="BCO03", holder_name="Padaria Bom Grão Ltda",
                   holder_type="PJ", document_masked=_doc(rng, pj=True),
                   opened_at=now - timedelta(days=1500))
    db.add(shop)
    for day in range(30):
        for _ in range(22):
            tx(rng.choice(normal), shop, rng.uniform(15, 180),
               now - timedelta(days=day, minutes=rng.randint(130, 900)))
    for _ in range(25):
        tx(rng.choice(normal), shop, rng.uniform(15, 180), now - timedelta(minutes=rng.randint(5, 115)))

    # --------------------------------------------------- cenário 3: república (falso positivo)
    rep = new_acc("ACC-900020", "BCO12", "Mariana Kehl", 20)
    landlord = normal[7]
    roommates = [rng.choice(by_inst[c]) for c in ["BCO01", "BCO02", "BCO05", "BCO07", "BCO09", "BCO14"]]
    rent_in = 0.0
    for r in roommates:
        amount = 720.0
        rent_in += amount
        tx(r, rep, amount, now - timedelta(minutes=rng.randint(50, 100)))
    tx(rep, landlord, rent_in * 0.95, now - timedelta(minutes=20), "TED")

    db.add_all(txs)
    db.flush()

    # contestações de 4 vítimas da conta-laranja
    for t in rng.sample(victim_txs, 4):
        db.add(Dispute(transaction_id=t.id, reason=rng.choice(DISPUTE_REASONS),
                       created_at=now - timedelta(minutes=rng.randint(5, 15))))
    db.flush()

    scoring.ensure_weights(db)
    results = scoring.scan(db)
    db.commit()
    return {
        "accounts": len(normal) + 6,
        "transactions": len(txs),
        "cases_opened": sum(1 for r in results if r[2]),
        "scenarios": {"mule_ring": "ACC-900001", "legit_shop": "ACC-900010", "student_rent": "ACC-900020"},
    }

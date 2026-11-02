"""Agente Investigador: grafo de relacionamento entre contas a partir das transferências.

É aqui que aparece a tese do SafeOne: cada banco enxerga só a sua parte do fluxo; a
infraestrutura enxerga o desenho inteiro (origem espalhada, destino concentrado, repasse).
"""
from collections import defaultdict, deque
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Case, Transaction, utcnow
from app.services.scoring import ACTIVE_CASE_STATUSES


def build_network(db: Session, account_id: str, hours: int = 24, depth: int = 2) -> dict:
    since = utcnow() - timedelta(hours=hours)
    txs = db.scalars(select(Transaction).where(Transaction.created_at > since)).all()

    out_edges: dict[str, list[Transaction]] = defaultdict(list)
    in_edges: dict[str, list[Transaction]] = defaultdict(list)
    for t in txs:
        out_edges[t.source_account_id].append(t)
        in_edges[t.dest_account_id].append(t)

    # BFS nos dois sentidos, até 'depth' saltos a partir da conta investigada
    dist = {account_id: 0}
    queue = deque([account_id])
    while queue:
        node = queue.popleft()
        if dist[node] >= depth:
            continue
        neighbours = [t.dest_account_id for t in out_edges[node]] + [
            t.source_account_id for t in in_edges[node]
        ]
        for nb in neighbours:
            if nb not in dist:
                dist[nb] = dist[node] + 1
                queue.append(nb)

    nodes_ids = set(dist)
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(nodes_ids)))}
    flagged = set(
        db.scalars(
            select(Case.account_id).where(
                Case.account_id.in_(nodes_ids), Case.status.in_(ACTIVE_CASE_STATUSES + ("approved",))
            )
        )
    )

    # agrega arestas origem->destino
    agg: dict[tuple[str, str], dict] = {}
    for t in txs:
        if t.source_account_id in nodes_ids and t.dest_account_id in nodes_ids:
            key = (t.source_account_id, t.dest_account_id)
            e = agg.setdefault(key, {"total": 0.0, "count": 0, "first": t.created_at, "last": t.created_at})
            e["total"] += t.amount
            e["count"] += 1
            e["first"] = min(e["first"], t.created_at)
            e["last"] = max(e["last"], t.created_at)

    now = utcnow()
    nodes = [
        {
            "account_id": aid,
            "institution_code": acc.institution_code,
            "holder_name": acc.holder_name,
            "age_days": (now - acc.opened_at).days,
            "status": acc.status,
            "hops": dist[aid],
            "has_case": aid in flagged,
        }
        for aid, acc in accounts.items()
    ]
    edges = [
        {
            "source": s,
            "target": d,
            "total_amount": round(e["total"], 2),
            "count": e["count"],
            "first_at": e["first"],
            "last_at": e["last"],
        }
        for (s, d), e in agg.items()
    ]

    inbound = [e for e in edges if e["target"] == account_id]
    outbound = [e for e in edges if e["source"] == account_id]
    total_in = sum(e["total_amount"] for e in inbound)
    total_out = sum(e["total_amount"] for e in outbound)
    source_institutions = {accounts[e["source"]].institution_code for e in inbound}

    # destinos de 2º salto: para onde o dinheiro seguiu depois de sair da conta
    downstream = [
        {
            "account_id": e["target"],
            "institution_code": accounts[e["target"]].institution_code,
            "received": e["total_amount"],
            "age_days": (now - accounts[e["target"]].opened_at).days,
            "forwarded_onward": round(
                sum(x["total_amount"] for x in edges if x["source"] == e["target"]), 2
            ),
        }
        for e in sorted(outbound, key=lambda x: -x["total_amount"])
    ]

    return {
        "account_id": account_id,
        "hours": hours,
        "depth": depth,
        "summary": {
            "accounts_in_network": len(nodes),
            "institutions_in_network": len({n["institution_code"] for n in nodes}),
            "source_institutions": len(source_institutions),
            "inbound_total": round(total_in, 2),
            "outbound_total": round(total_out, 2),
            "estimated_remaining": round(max(0.0, total_in - total_out), 2),
            "flagged_neighbours": sorted(flagged - {account_id}),
        },
        "downstream": downstream,
        "nodes": nodes,
        "edges": edges,
    }

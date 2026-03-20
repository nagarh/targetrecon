"""STRING DB client — protein-protein interaction network."""
from __future__ import annotations

from targetrecon.clients.http import build_client


async def fetch_interactions(
    uniprot_id: str,
    gene_name: str | None = None,
    limit: int = 30,
    min_score: float = 0.4,
    species: int = 9606,
) -> list[dict]:
    """Return top `limit` interaction partners from STRING for a UniProt ID."""
    identifier = uniprot_id

    params = {
        "identifiers": identifier,
        "species": species,
        "limit": limit,
        "caller_identity": "targetrecon",
        "format": "json",
    }

    async with build_client(timeout=20.0) as client:
        try:
            resp = await client.get(
                "https://string-db.org/api/json/interaction_partners",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

    if not isinstance(data, list):
        return []

    results = []
    for item in data:
        score = float(item.get("score", 0))
        if score < min_score:
            continue
        results.append({
            "gene_a": item.get("preferredName_A", ""),
            "gene_b": item.get("preferredName_B", ""),
            "score": round(score, 3),
            "experimental": round(float(item.get("escore", 0)), 3),
            "database": round(float(item.get("dscore", 0)), 3),
            "textmining": round(float(item.get("tscore", 0)), 3),
            "coexpression": round(float(item.get("ascore", 0)), 3),
            "string_id_b": item.get("stringId_B", ""),
        })

    return sorted(results, key=lambda x: -x["score"])

"""ID resolution: gene name / UniProt accession / ChEMBL ID → (uniprot_id, chembl_id)."""
from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass, field


@dataclass
class CompoundTarget:
    """A target that a compound has been tested against."""
    target_chembl_id: str
    target_name: str
    target_type: str
    uniprot_id: str | None
    gene_name: str | None
    organism: str
    best_pchembl: float | None
    num_activities: int


async def fetch_compound_targets(molecule_chembl_id: str, limit: int = 20) -> list[CompoundTarget]:
    """
    Given a molecule ChEMBL ID, return all unique protein targets it has been
    tested against, sorted by best pChEMBL (most potent first).
    """
    from targetrecon.clients.http import build_client, safe_get

    # Fetch activities for this molecule, grouped by target
    url = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
    params = {
        "molecule_chembl_id": molecule_chembl_id,
        "target_type": "SINGLE PROTEIN",
        "pchembl_value__isnull": "false",
        "limit": "1000",
        "offset": "0",
    }
    async with build_client(timeout=30.0) as client:
        data = await safe_get(client, url, params=params)

    if not data:
        return []

    # Aggregate by target
    target_map: dict[str, dict] = {}
    for act in data.get("activities", []):
        tid = act.get("target_chembl_id")
        if not tid:
            continue
        pc = _safe_float(act.get("pchembl_value"))
        if tid not in target_map:
            target_map[tid] = {
                "target_chembl_id": tid,
                "target_name": act.get("target_pref_name") or "",
                "target_type": act.get("target_type") or "",
                "organism": act.get("target_organism") or "",
                "best_pchembl": pc,
                "num_activities": 1,
            }
        else:
            target_map[tid]["num_activities"] += 1
            if pc and (target_map[tid]["best_pchembl"] is None or pc > target_map[tid]["best_pchembl"]):
                target_map[tid]["best_pchembl"] = pc

    if not target_map:
        return []

    # Resolve UniProt/gene for each target (parallel)
    import asyncio
    results: list[CompoundTarget] = []

    async def _enrich(entry: dict) -> CompoundTarget:
        uid = await _resolve_uniprot_from_chembl(entry["target_chembl_id"])
        gene = None
        if uid:
            from targetrecon.clients.uniprot import fetch_uniprot
            info = await fetch_uniprot(uid)
            if info:
                uid = info.uniprot_id  # canonical
                gene = info.gene_name
        return CompoundTarget(
            target_chembl_id=entry["target_chembl_id"],
            target_name=entry["target_name"],
            target_type=entry["target_type"],
            uniprot_id=uid,
            gene_name=gene,
            organism=entry["organism"],
            best_pchembl=entry["best_pchembl"],
            num_activities=entry["num_activities"],
        )

    tasks = [_enrich(e) for e in list(target_map.values())[:limit]]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    results.sort(key=lambda t: t.best_pchembl or 0.0, reverse=True)
    return list(results)


def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class QueryType(str, Enum):
    GENE = "gene"
    UNIPROT = "uniprot"
    CHEMBL = "chembl"


def classify_query(query: str) -> QueryType:
    q = query.strip().upper()
    # UniProt accession pattern
    if re.match(
        r'^[OPQ][0-9][A-Z0-9]{3}[0-9]$'
        r'|^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$',
        q,
    ):
        return QueryType.UNIPROT
    if q.startswith("CHEMBL") and q[6:].isdigit():
        return QueryType.CHEMBL
    return QueryType.GENE


async def resolve_ids(query: str) -> tuple[str | None, str | None]:
    """Return (uniprot_id, chembl_id) for any query type."""
    from targetrecon.clients.uniprot import fetch_uniprot, search_gene
    from targetrecon.clients.chembl import resolve_target_chembl_id

    qtype = classify_query(query)

    if qtype == QueryType.UNIPROT:
        uniprot_id = query.upper()
        info = await fetch_uniprot(uniprot_id)
        chembl_id = info.chembl_id if info else None
        if not chembl_id:
            chembl_id = await resolve_target_chembl_id(uniprot_id)
        return uniprot_id, chembl_id

    elif qtype == QueryType.CHEMBL:
        chembl_id = query.upper()
        uniprot_id = await _resolve_uniprot_from_chembl(chembl_id)
        return uniprot_id, chembl_id

    else:  # GENE
        uniprot_id = await search_gene(query)
        if not uniprot_id:
            return None, None
        info = await fetch_uniprot(uniprot_id)
        chembl_id = info.chembl_id if info else None
        if not chembl_id:
            chembl_id = await resolve_target_chembl_id(uniprot_id)
        return uniprot_id, chembl_id


async def _resolve_uniprot_from_chembl(chembl_id: str) -> str | None:
    from targetrecon.clients.http import build_client, safe_get
    from targetrecon.clients.uniprot import search_gene

    # Step 1: Try to fetch it as a ChEMBL target
    url = f"https://www.ebi.ac.uk/chembl/api/data/target/{chembl_id}.json"
    async with build_client() as client:
        data = await safe_get(client, url)

    if data:
        # ChEMBL uses both "UniProt" and "UniProtKB" as xref_src_db values
        for comp in data.get("target_components", []):
            for xref in comp.get("target_component_xrefs", []):
                if xref.get("xref_src_db") in ("UniProt", "UniProtKB"):
                    uid = xref.get("xref_id", "").strip()
                    if uid:
                        return uid
        # If it is a protein family / complex, try gene_name from the target name
        target_name = data.get("pref_name", "")
        if target_name and data.get("target_type") in (
            "PROTEIN FAMILY", "PROTEIN COMPLEX", "SELECTIVITY GROUP"
        ):
            # Last resort: search UniProt by the target preferred name
            uid = await search_gene(target_name)
            if uid:
                return uid

    # Step 2: It may be a molecule (compound) ID, not a target.
    # Try to find the most common target for this molecule via ChEMBL activities.
    mol_url = f"https://www.ebi.ac.uk/chembl/api/data/activity.json"
    params = {"molecule_chembl_id": chembl_id, "limit": "5", "pchembl_value__isnull": "false"}
    async with build_client() as client:
        act_data = await safe_get(client, mol_url, params=params)
    if act_data:
        activities = act_data.get("activities", [])
        if activities:
            # Pick the target from the first activity and recurse
            target_id = activities[0].get("target_chembl_id")
            if target_id and target_id != chembl_id:
                return await _resolve_uniprot_from_chembl(target_id)

    return None

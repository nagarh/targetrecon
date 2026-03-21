"""BindingDB REST API client."""
from __future__ import annotations

import math

from targetrecon.clients.http import build_client
from targetrecon.models import BioactivityRecord

# New REST endpoint (axis2/BDBService was retired)
BINDINGDB_URL = "http://bindingdb.org/rest/getLigandsByUniprots"


async def fetch_bioactivities_by_uniprot(
    uniprot_id: str,
    limit: int = 500,
) -> list[BioactivityRecord]:
    params = {
        "uniprot": uniprot_id,
        "cutoff": "10000",
        "response": "application/json",
    }

    async with build_client(timeout=12.0) as client:
        try:
            resp = await client.get(BINDINGDB_URL, params=params)
            resp.raise_for_status()
        except Exception:
            return []

    try:
        data = resp.json()
    except Exception:
        return []

    # BindingDB has a typo in the response key: "getLindsByUniprotsResponse"
    wrapper = (
        data.get("getLigandsByUniprotsResponse")
        or data.get("getLindsByUniprotsResponse")
        or {}
    )
    affinities = wrapper.get("affinities", [])
    if isinstance(affinities, dict):
        affinities = [affinities]

    records: list[BioactivityRecord] = []
    for aff in affinities:
        # SMILES field is "smile" (singular) in BindingDB REST responses
        smiles = (
            aff.get("smile") or aff.get("smiles") or aff.get("SMILES") or ""
        ).strip()
        # Strip BindingDB extended SMILES notation (|r,wU:...|) — RDKit doesn't need it
        if " |" in smiles:
            smiles = smiles[:smiles.index(" |")]
        if not smiles:
            continue

        atype = (aff.get("affinity_type") or "").strip()
        value = _parse_float(aff.get("affinity"))
        pchembl = _to_pchembl(value)

        records.append(
            BioactivityRecord(
                smiles=smiles,
                activity_type=atype or None,
                value=value,
                pchembl_value=pchembl,
                source="BindingDB",
            )
        )

    # Sort by pChEMBL descending so most potent come first, then apply limit
    records.sort(key=lambda r: r.pchembl_value or 0.0, reverse=True)
    return records[:limit]


def _parse_float(s: object) -> float | None:
    if s is None:
        return None
    try:
        v = float(str(s).strip().lstrip("><~≈"))
        return v if 0 < v <= 1e7 else None
    except (ValueError, TypeError):
        return None


def _to_pchembl(value_nm: float | None) -> float | None:
    if value_nm and value_nm > 0:
        return round(-math.log10(value_nm * 1e-9), 2)
    return None

"""ChEMBL REST API client."""
from __future__ import annotations

from targetrecon.clients.http import build_client, safe_get
from targetrecon.models import BioactivityRecord

CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data"


async def resolve_target_chembl_id(uniprot_id: str) -> str | None:
    """Resolve UniProt → ChEMBL target ID."""
    url = f"{CHEMBL_API}/target/search.json"
    params = {"q": uniprot_id, "limit": 5}
    async with build_client() as client:
        data = await safe_get(client, url, params=params)
    if not data:
        return None
    for target in data.get("targets", []):
        # Prefer single protein targets
        if target.get("target_type") == "SINGLE PROTEIN":
            return target.get("target_chembl_id")
    targets = data.get("targets", [])
    return targets[0].get("target_chembl_id") if targets else None


async def fetch_bioactivities_by_target(
    chembl_id: str,
    limit: int = 500,
    min_pchembl: float | None = None,
) -> list[BioactivityRecord]:
    records: list[BioactivityRecord] = []
    url = f"{CHEMBL_API}/activity.json"
    params: dict = {
        "target_chembl_id": chembl_id,
        "pchembl_value__isnull": "false",
        "limit": str(min(limit, 1000)),
        "offset": "0",
    }
    if min_pchembl is not None:
        params["pchembl_value__gte"] = str(min_pchembl)

    async with build_client(timeout=60.0) as client:
        while len(records) < limit:
            data = await safe_get(client, url, params=params)
            if not data:
                break

            activities = data.get("activities", [])
            if not activities:
                break

            for act in activities:
                smiles = act.get("canonical_smiles")
                if not smiles:
                    continue

                pchembl = _safe_float(act.get("pchembl_value"))
                value = _safe_float(act.get("standard_value"))

                records.append(
                    BioactivityRecord(
                        molecule_chembl_id=act.get("molecule_chembl_id"),
                        smiles=smiles,
                        activity_type=act.get("standard_type", ""),
                        value=value,
                        pchembl_value=pchembl,
                        source="ChEMBL",
                        assay_id=act.get("assay_chembl_id"),
                        name=act.get("molecule_pref_name"),
                    )
                )

            next_url = data.get("page_meta", {}).get("next")
            if not next_url or len(records) >= limit:
                break
            # ChEMBL next URL starts with /chembl/api/...
            if next_url.startswith("/"):
                url = f"https://www.ebi.ac.uk{next_url}"
            else:
                url = next_url
            params = {}  # baked into URL

    return records[:limit]


def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

"""AlphaFold Database API client."""
from __future__ import annotations

from targetrecon.clients.http import build_client, safe_get
from targetrecon.models import AlphaFoldModel

AF_API = "https://alphafold.ebi.ac.uk/api/prediction"


async def fetch_alphafold(uniprot_id: str) -> AlphaFoldModel | None:
    async with build_client(timeout=20.0) as client:
        data = await safe_get(client, f"{AF_API}/{uniprot_id}")

    if not data:
        return None

    # API returns a list
    if isinstance(data, list):
        if not data:
            return None
        entry = data[0]
    else:
        entry = data

    return AlphaFoldModel(
        uniprot_id=uniprot_id,
        pdb_url=entry.get("pdbUrl"),
        model_url=entry.get("cifUrl"),
        version=entry.get("latestVersion", 4),
        mean_plddt=entry.get("meanConfidence"),
        sequence_length=entry.get("uniprotEnd"),
    )

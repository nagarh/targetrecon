"""AlphaFold Database API client."""
from __future__ import annotations

from targetrecon.clients.http import build_client, safe_get
from targetrecon.models import AlphaFoldModel

AF_API = "https://alphafold.ebi.ac.uk/api/prediction"


async def fetch_alphafold(uniprot_id: str) -> AlphaFoldModel | None:
    async with build_client(timeout=20.0) as client:
        data = await safe_get(client, f"{AF_API}/{uniprot_id}")

    if data:
        # API returns a list
        entry = data[0] if isinstance(data, list) else data
        return AlphaFoldModel(
            uniprot_id=uniprot_id,
            pdb_url=entry.get("pdbUrl"),
            model_url=entry.get("cifUrl"),
            version=entry.get("latestVersion", 4),
            mean_plddt=entry.get("globalMetricValue") or entry.get("meanConfidence"),
            sequence_length=entry.get("uniprotEnd"),
        )

    # API failed (intermittent 500) — fall back to standard URL pattern
    # AlphaFold file naming is predictable: AF-{uniprot_id}-F1-model_v{version}.pdb
    fallback_url = f"https://alphafold.ebi.ac.uk/files/AF-{uniprot_id}-F1-model_v6.pdb"
    return AlphaFoldModel(
        uniprot_id=uniprot_id,
        pdb_url=fallback_url,
        model_url=f"https://alphafold.ebi.ac.uk/files/AF-{uniprot_id}-F1-model_v6.cif",
        version=6,
    )
